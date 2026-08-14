import 'package:flutter/material.dart';
import '../api.dart';
import '../main.dart';
import '../widgets/common.dart';
import 'guide.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeData {
  final List<dynamic> exercises;
  final List<dynamic> sessions;
  const _HomeData({required this.exercises, required this.sessions});
}

/// 홈에서 쓰는 파생 지표 묶음. 전부 `/sessions` 응답만으로 프런트에서 산출한다.
class _WeekStats {
  final int count;
  final int totalReps;
  final double? avgScore;

  /// 세트당 평균 렙 = 이번 주 총 렙 / 이번 주 총 세트 수. 세트 기록이 없으면 null.
  final double? repsPerSet;

  /// 일~토 7칸 렙 합계.
  final List<num> weeklyReps;

  /// 오늘의 요일 인덱스(일=0). 막대 강조용.
  final int todayIndex;

  /// 오늘(또는 어제)부터 역순으로 공백 없이 이어지는 운동일 수. 주 경계를 넘어 센다.
  final int streak;

  const _WeekStats({
    required this.count,
    required this.totalReps,
    required this.avgScore,
    required this.repsPerSet,
    required this.weeklyReps,
    required this.todayIndex,
    required this.streak,
  });

  factory _WeekStats.from(List<dynamic> sessions) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final todayIndex = now.weekday % 7; // 일=0 ... 토=6
    final weekStart = today.subtract(Duration(days: todayIndex));

    final weeklyReps = List<num>.filled(7, 0);
    var count = 0;
    var totalReps = 0;
    var scoreSum = 0.0;
    var scoreCount = 0;
    var setCount = 0;
    var setReps = 0;
    final activeDays = <DateTime>{};

    for (final raw in sessions) {
      final s = raw as Map<String, dynamic>;
      final parsed = DateTime.tryParse(s['date']?.toString() ?? '');
      if (parsed == null) continue;
      final day = DateTime(parsed.year, parsed.month, parsed.day);
      activeDays.add(day);

      final offset = day.difference(weekStart).inDays;
      if (offset < 0 || offset > 6) continue;

      final reps = (s['total_reps'] as num? ?? 0).toInt();
      count += 1;
      totalReps += reps;
      weeklyReps[offset] = weeklyReps[offset] + reps;

      final score = s['avg_form_score'] as num?;
      if (score != null) {
        scoreSum += score.toDouble();
        scoreCount += 1;
      }

      final sets = s['sets'];
      if (sets is List && sets.isNotEmpty) {
        setCount += sets.length;
        setReps += reps;
      }
    }

    // 스트릭 — 오늘 기록이 없으면 어제를 기점으로 삼는다(오늘이 아직 안 끝났으므로 끊지 않음).
    var cursor = activeDays.contains(today) ? today : today.subtract(const Duration(days: 1));
    var streak = 0;
    while (activeDays.contains(cursor)) {
      streak += 1;
      cursor = cursor.subtract(const Duration(days: 1));
    }

    return _WeekStats(
      count: count,
      totalReps: totalReps,
      avgScore: scoreCount == 0 ? null : scoreSum / scoreCount,
      repsPerSet: setCount == 0 ? null : setReps / setCount,
      weeklyReps: weeklyReps,
      todayIndex: todayIndex,
      streak: streak,
    );
  }
}

class _HomeScreenState extends State<HomeScreen> {
  late Future<_HomeData> _dataFuture;

  @override
  void initState() {
    super.initState();
    _dataFuture = _load();
  }

  Future<_HomeData> _load() async {
    final results = await Future.wait([
      Api.instance.getExercises(),
      Api.instance.getSessions(),
    ]);
    return _HomeData(exercises: results[0], sessions: results[1]);
  }

  Future<void> _reload() {
    final future = _load();
    setState(() => _dataFuture = future);
    return future;
  }

  @override
  Widget build(BuildContext context) {
    // 크리스탈 글라스: 밝은 백드롭 위에 히어로 한 장만 프로스티드 글라스로 띄우고,
    // 반복되는 스탯필·운동 그리드는 솔리드 색면(BlockCard)으로 둔다(스크롤 성능).
    return GradientBackground(
      child: Scaffold(
        backgroundColor: Colors.transparent,
        // iOS 라지 타이틀 — 스크롤과 무관하게 상단에 고정, 모든 상태(로딩/에러/빈/데이터)에서 유지.
        body: SafeArea(
          bottom: false,
          child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 10, 20, 12),
              child: _Wordmark(),
            ),
            Expanded(
              child: FutureBuilder<_HomeData>(
                future: _dataFuture,
                builder: (context, snapshot) {
                  if (snapshot.connectionState != ConnectionState.done) {
                    return const SkeletonList();
                  }
                  if (snapshot.hasError) {
                    return Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: ErrorCard(message: '불러오기 실패: ${snapshot.error}', onRetry: _reload),
                      ),
                    );
                  }
                  final exercises = snapshot.data?.exercises ?? [];
                  final sessions = snapshot.data?.sessions ?? [];
                  if (exercises.isEmpty) {
                    return EmptyState(
                      icon: Icons.sports_gymnastics,
                      message: '등록된 운동이 없습니다.',
                      actionLabel: '새로고침',
                      onAction: _reload,
                    );
                  }
                  final stats = _WeekStats.from(sessions);
                  return RefreshIndicator(
                    onRefresh: _reload,
                    color: AppColors.primary,
                    child: ListView(
                      padding: const EdgeInsets.fromLTRB(16, 4, 16, 28),
                      children: [
                        _HeroBlock(stats: stats),
                        if (stats.count > 0) ...[
                          const SizedBox(height: 12),
                          _StatPillRow(stats: stats),
                        ],
                        const SizedBox(height: 24),
                        const _SectionTitle('운동 선택'),
                        const SizedBox(height: 12),
                        _ExerciseGrid(exercises: exercises),
                      ],
                    ),
                  );
                },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 시안 홈 상단 워드마크 — 'THE FIT' 이탤릭.
/// 사용자가 주황↔초록 그라데이션을 금지했으므로 솔리드 코랄로 쓴다(시안은 그라데이션이지만 지시 우선).
/// 26px 이탤릭 볼드 = 큰 텍스트라 오프화이트 배경 위 primaryText로 3:1 충족.
class _Wordmark extends StatelessWidget {
  const _Wordmark();

  @override
  Widget build(BuildContext context) {
    return Semantics(
      header: true,
      label: 'The Fit',
      child: const Text(
        'THE FIT',
        style: TextStyle(
          fontSize: 26,
          fontWeight: FontWeight.w800,
          fontStyle: FontStyle.italic,
          letterSpacing: -0.8,
          color: AppColors.primaryText, // 솔리드 코랄 (#C63D22)
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String text;
  const _SectionTitle(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontSize: 18,
        fontWeight: FontWeight.w800,
        color: AppColors.foreground,
      ),
    );
  }
}

/// 화면 상단을 장악하는 프로스티드 글라스 히어로(화면에서 유일한 GlassCard — 포컬).
/// 이번 주 총 렙(그라데이션 거대 숫자) + 연속일 배지 + 요일별 볼륨 막대를 한 덩어리로 묶는다.
class _HeroBlock extends StatelessWidget {
  final _WeekStats stats;
  const _HeroBlock({required this.stats});

  static const _dayLabels = ['일', '월', '화', '수', '목', '금', '토'];

  /// 글라스 위 텍스트/막대 토큰 — 밝은 글라스 실효면(#FFF7F3) 위 잉크 + 슬레이트 muted.
  /// (cream 슬롯이 ink 전경 + 라이트 배경 muted를 이미 검증해 그대로 재사용한다.)
  static const _glassInk = AppBlocks.cream;

  @override
  Widget build(BuildContext context) {
    final hasData = stats.count > 0;

    return GlassCard(
      padding: const EdgeInsets.fromLTRB(22, 22, 22, 18),
      radius: 26,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Expanded(
                child: Text(
                  '이번 주',
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, letterSpacing: 0.4),
                ),
              ),
              // 스트릭이 있을 때만 코랄 배지로 브랜드 강조. 0일이면 배지를 숨긴다.
              if (stats.streak > 0)
                StreakBadge(days: stats.streak, style: AppBlocks.gochujang),
            ],
          ),
          const SizedBox(height: 18),
          if (!hasData)
            // 글라스 히어로 안의 빈 상태 — 글라스 실효면 위 muted(7.09:1)로 그린다.
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.event_busy, color: _glassInk.mutedOr, size: 34),
                const SizedBox(height: 10),
                Text(
                  '이번 주 운동 기록이 없어요.\n아래에서 운동을 골라 첫 세트를 시작해보세요.',
                  style: TextStyle(color: _glassInk.mutedOr, fontSize: 13, height: 1.4),
                ),
              ],
            )
          else ...[
            BigStat(
              style: _glassInk,
              // 시안은 큰 숫자를 darken한다 — 흰 카드 위 primaryText(#C63D22, 5.13:1)로 칠한다.
              // (coral_mid는 흰 위 3.00으로 큰텍스트 경계라 더 안전한 darken 코랄을 쓴다.)
              valueColor: AppColors.primaryText,
              value: '${stats.totalReps}',
              unit: '회',
              caption: '이번 주 총 렙 수',
              size: 64,
            ),
            const SizedBox(height: 18),
            MiniBarChart(
              values: stats.weeklyReps,
              style: _glassInk,
              labels: _dayLabels,
              showValues: true,
              highlightIndex: stats.todayIndex,
              height: 116,
              semanticLabel: '요일별 총 렙 수. '
                  '${List.generate(7, (i) => '${_dayLabels[i]}요일 ${stats.weeklyReps[i]}회').join(', ')}',
            ),
          ],
        ],
      ),
    );
  }
}

/// 서로 다른 솔리드 색면을 가진 스탯 배지 3연.
class _StatPillRow extends StatelessWidget {
  final _WeekStats stats;
  const _StatPillRow({required this.stats});

  @override
  Widget build(BuildContext context) {
    final avg = stats.avgScore;
    final perSet = stats.repsPerSet;
    // IntrinsicHeight로 감싼다: ListView 안에서는 세로(cross axis) 제약이 무한대라
    // stretch 단독으로는 "BoxConstraints forces an infinite height"가 난다.
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 시안 스탯 3연: 흰 카드 / 페일 코랄 / 페일 틸 — 전부 라이트 톤이라 아웃라인으로 면을 세운다.
          // (시안은 여기서 솔리드 코랄을 쓰지 않는다 — 코랄 솔리드는 스트릭 배지 한 곳에만.)
          Expanded(
            child: StatPill(
              style: AppBlocks.cream,
              outlined: true, // 흰 카드는 scaffold와 1.05:1 → 아웃라인 필수
              value: '${stats.count}',
              unit: '회',
              label: '운동 횟수',
              icon: Icons.event_available_rounded,
              center: true,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: StatPill(
              style: AppBlocks.tintGochujang, // 페일 코랄 틴트(시안 평균 폼 점수 카드)
              outlined: true,
              value: avg == null ? '-' : '${avg.round()}',
              unit: avg == null ? null : '점',
              label: '평균 폼 점수',
              icon: Icons.verified_rounded,
              center: true,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: StatPill(
              style: AppBlocks.tintCrimson,
              outlined: true, // 페일 틸도 scaffold 위에서 아웃라인 필요
              value: perSet == null ? '-' : perSet.toStringAsFixed(1),
              unit: perSet == null ? null : '회',
              label: '세트당 렙',
              icon: Icons.repeat_rounded,
              center: true,
            ),
          ),
        ],
      ),
    );
  }
}

/// 2열 벤토 그리드. 지원 운동 타일은 전부 같은 밝은 톤으로 통일하고, 미지원은 중립(크림)으로 내린다.
class _ExerciseGrid extends StatelessWidget {
  final List<dynamic> exercises;
  const _ExerciseGrid({required this.exercises});

  /// 지원 운동 타일은 전부 같은 밝은 톤(페일 코랄, 글라스풍)으로 통일한다 — 스쿼트=푸시업.
  /// 진한 솔리드 코랄(gochujang) 덩어리를 걷어내 "너무 진하다"를 덜어냈다. 코랄은 큰숫자·CTA에만.
  static const _support = AppBlocks.tintGochujang;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const gap = 12.0;
        final width = (constraints.maxWidth - gap) / 2;
        final tiles = <Widget>[];
        // 지원(측정 가능) 운동을 앞으로. 순서는 안정 정렬이라 각 그룹 내 원래 순서는 유지된다.
        final ordered = [...exercises]..sort((a, b) {
            final sa = (a as Map<String, dynamic>)['supported'] as bool? ?? false;
            final sb = (b as Map<String, dynamic>)['supported'] as bool? ?? false;
            return sa == sb ? 0 : (sa ? -1 : 1);
          });
        for (final raw in ordered) {
          final ex = raw as Map<String, dynamic>;
          final supported = ex['supported'] as bool? ?? false;
          final style = supported ? _support : AppBlocks.cream;
          tiles.add(SizedBox(
            width: width,
            height: 150,
            child: _ExerciseTile(
              ex: ex,
              style: style,
              supported: supported,
              onTap: supported
                  ? () => Navigator.of(context)
                      .push(fadeRoute(context, (_) => GuideScreen(exercise: ex)))
                  : null,
            ),
          ));
        }
        return Wrap(spacing: gap, runSpacing: gap, children: tiles);
      },
    );
  }
}

class _ExerciseTile extends StatelessWidget {
  final Map<String, dynamic> ex;
  final BlockStyle style;
  final bool supported;
  final VoidCallback? onTap;

  const _ExerciseTile({
    required this.ex,
    required this.style,
    required this.supported,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final name = ex['name'] as String? ?? '';
    final target = ex['target'] as String? ?? '';
    final difficulty = ex['difficulty'] as String? ?? '';
    final meta = [target, difficulty].where((s) => s.isNotEmpty).join(' · ');

    return BlockCard(
      style: style,
      // 지원(페일 코랄)·미지원(크림) 둘 다 scaffold와 밝기가 가까운 라이트 톤 → 아웃라인으로 면을 세운다.
      outlined: true,
      onTap: onTap,
      padding: const EdgeInsets.all(16),
      semanticLabel: supported
          ? '$name, $meta, 가이드 열기'
          : '$name, $meta, 준비 중이라 선택할 수 없음',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: style.foreground.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  supported ? Icons.fitness_center_rounded : Icons.lock_clock_rounded,
                  size: 20,
                  color: style.foreground,
                ),
              ),
              const Spacer(),
              // 상태를 색이 아니라 아이콘/텍스트로도 못 박는다 (WCAG 1.4.1).
              if (supported)
                Icon(Icons.arrow_forward_rounded, size: 18, color: style.mutedOr)
              else
                Text(
                  '준비 중',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: style.mutedOr,
                  ),
                ),
            ],
          ),
          const Spacer(),
          Text(
            name,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, height: 1.2),
          ),
          const SizedBox(height: 5),
          Text(
            meta,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 12, color: style.mutedOr),
          ),
        ],
      ),
    );
  }
}
