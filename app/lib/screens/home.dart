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
    return Scaffold(
      appBar: AppBar(title: const Text('운동 선택')),
      body: FutureBuilder<_HomeData>(
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
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
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

/// 화면 상단을 장악하는 네이비 솔리드 색면.
/// 이번 주 총 렙(거대 숫자) + 연속일 배지 + 요일별 볼륨 막대를 한 덩어리로 묶는다.
class _HeroBlock extends StatelessWidget {
  final _WeekStats stats;
  const _HeroBlock({required this.stats});

  static const _dayLabels = ['일', '월', '화', '수', '목', '금', '토'];

  @override
  Widget build(BuildContext context) {
    const style = AppBlocks.navy;
    final hasData = stats.count > 0;

    return BlockCard(
      style: style,
      padding: const EdgeInsets.fromLTRB(22, 22, 22, 18),
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
              StreakBadge(
                days: stats.streak,
                style: stats.streak > 0 ? AppBlocks.crimson : AppBlocks.darkNeutral,
              ),
            ],
          ),
          const SizedBox(height: 18),
          if (!hasData)
            const EmptyState(
              icon: Icons.event_busy,
              message: '이번 주 운동 기록이 없어요.\n아래에서 운동을 골라 첫 세트를 시작해보세요.',
              compact: true,
              dark: true,
            )
          else ...[
            BigStat(
              style: style,
              value: '${stats.totalReps}',
              unit: '회',
              caption: '이번 주 총 렙 수',
              size: 60,
            ),
            const SizedBox(height: 18),
            MiniBarChart(
              values: stats.weeklyReps,
              style: style,
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
          Expanded(
            child: StatPill(
              style: AppBlocks.crimson,
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
              style: AppBlocks.gochujang,
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
              style: AppBlocks.navy,
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

/// 2열 벤토 그리드. 지원 운동은 솔리드 색면을 돌려 쓰고, 미지원은 중립(크림+아웃라인)으로 내린다.
class _ExerciseGrid extends StatelessWidget {
  final List<dynamic> exercises;
  const _ExerciseGrid({required this.exercises});

  /// 지원 운동에만 순환 적용. 미지원 카드는 이 순환을 소비하지 않는다.
  static const _cycle = [AppBlocks.gochujang, AppBlocks.navy, AppBlocks.crimson];

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const gap = 12.0;
        final width = (constraints.maxWidth - gap) / 2;
        var supportedSeen = 0;
        final tiles = <Widget>[];
        for (final raw in exercises) {
          final ex = raw as Map<String, dynamic>;
          final supported = ex['supported'] as bool? ?? false;
          final style = supported ? _cycle[supportedSeen++ % _cycle.length] : AppBlocks.cream;
          tiles.add(SizedBox(
            width: width,
            height: 156,
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
      // 미지원 카드는 크림 = scaffold와 거의 같은 밝기 → 아웃라인으로 면을 세운다.
      outlined: !supported,
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
