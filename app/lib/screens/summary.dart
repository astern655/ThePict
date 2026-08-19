import 'package:flutter/material.dart';
import '../api.dart';
import '../main.dart';
import '../widgets/common.dart';
import 'root.dart';

/// 폼 점수 구간 → 구간 라벨 + 아이콘 + 강조 색.
/// 히어로가 글라스(밝은 실효면)로 바뀌면서 배경색으로 구간을 말하던 방식은 사라졌다.
/// 대신 구간을 [accent]로 전달한다 — 값은 [formScoreColor]와 같은 의미색(틸/앰버/레드)이라
/// 링 중앙 숫자 색과도 일치한다. 색만으로 전달하지 않으려 라벨/아이콘을 항상 함께 반환한다(WCAG 1.4.1).
/// accent는 전부 글라스 실효면(#FFF7F3) 위 ≥4.5:1(success 5.17 / secondary 4.74 / error 5.93).
({String label, IconData icon, Color accent}) _scoreBand(num? score) {
  if (score == null) {
    return (label: '점수 없음', icon: Icons.remove_rounded, accent: AppColors.foregroundMuted);
  }
  if (score >= 80) {
    return (label: '우수한 자세', icon: formScoreIcon(score), accent: AppColors.success);
  }
  if (score >= 60) {
    return (label: '무난한 자세', icon: formScoreIcon(score), accent: AppColors.secondary);
  }
  return (label: '자세 개선 필요', icon: formScoreIcon(score), accent: AppColors.error);
}

String _fmt(num n) => n == n.roundToDouble() ? n.round().toString() : n.toStringAsFixed(1);

class SummaryScreen extends StatefulWidget {
  final Map<String, dynamic> session;
  final Map<String, dynamic> exercise;
  const SummaryScreen({super.key, required this.session, required this.exercise});

  @override
  State<SummaryScreen> createState() => _SummaryScreenState();
}

class _SummaryScreenState extends State<SummaryScreen> {
  late Future<Map<String, dynamic>> _compareFuture;
  late Future<List<num>> _recentScoresFuture;

  /// 문장 분석. 세션 id가 없으면(=저장 전) 아예 만들지 않는다 → [_analysisSection]이 안내를 낸다.
  Future<Map<String, dynamic>>? _analysisFuture;

  String? get _sessionId => widget.session['id']?.toString();

  @override
  void initState() {
    super.initState();
    _compareFuture = Api.instance.getCompare(widget.exercise['id'].toString());
    _recentScoresFuture = _loadRecentScores();
    _analysisFuture = _loadAnalysis();
  }

  Future<Map<String, dynamic>>? _loadAnalysis() {
    final id = _sessionId;
    return id == null ? null : Api.instance.getSessionAnalysis(id);
  }

  void _retryAnalysis() => setState(() => _analysisFuture = _loadAnalysis());

  Future<List<num>> _loadRecentScores() async {
    final sessions = await Api.instance.getSessions();
    final sorted = [...sessions]..sort(
        (a, b) => (a as Map<String, dynamic>)['started_at']
            .toString()
            .compareTo((b as Map<String, dynamic>)['started_at'].toString()));
    final scores =
        sorted.map((s) => (s as Map<String, dynamic>)['avg_form_score'] as num? ?? 0).toList();
    return scores.length <= 7 ? scores : scores.sublist(scores.length - 7);
  }

  void _retryRecentScores() => setState(() => _recentScoresFuture = _loadRecentScores());

  void _retryCompare() => setState(() {
        _compareFuture = Api.instance.getCompare(widget.exercise['id'].toString());
      });

  static List<num> _reps(List<Map<String, dynamic>> sets) =>
      sets.map((s) => (s['reps'] as num?) ?? 0).toList();

  static List<Map<String, dynamic>> _setsOf(dynamic node) =>
      (((node as Map<String, dynamic>?)?['sets'] as List?) ?? const [])
          .cast<Map<String, dynamic>>();

  @override
  Widget build(BuildContext context) {
    final totalReps = widget.session['total_reps'] as num?;
    final avgScore = widget.session['avg_form_score'] as num?;
    final sets = ((widget.session['sets'] as List?) ?? const []).cast<Map<String, dynamic>>();
    final reps = _reps(sets);
    final band = _scoreBand(avgScore);

    // 시안 요약: 내비 바 없이 큰 타이틀 "세션 요약"(34px)을 본문 최상단에 둔다. 그 아래
    // 히어로(총 렙 + 폼 점수 링)·코치 노트·기록이 스크롤된다. 종료는 하단 코랄 '홈으로' 필로만.
    return GradientBackground(
      child: Scaffold(
        backgroundColor: Colors.transparent,
        body: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
            children: [
              _largeTitle('세션 요약'),
              _hero(context, band, totalReps, avgScore),
              const SizedBox(height: 28),
              // 점수 바로 아래가 문장 자리다 — "82점"이 무슨 뜻인지는 여기서만 알 수 있다.
              _sectionHeader('코치 노트'),
              _analysisSection(),
              const SizedBox(height: 28),
              _sectionHeader('기록'),
              _pillRow(sets, reps),
              const SizedBox(height: 14),
              _setBlock(sets, reps),
              const SizedBox(height: 14),
              _compareBlock(),
              const SizedBox(height: 14),
              _trendBlock(),
              const SizedBox(height: 32),
              GradientButton(
                onPressed: () => Navigator.of(context).pushAndRemoveUntil(
                  fadeRoute(context, (_) => const RootScreen()),
                  (route) => false,
                ),
                child: const Text('홈으로'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// iOS 큰 타이틀 — 34px bold 좌측, scaffold 위 짙은 전경(≈16:1). 코랄은 채움 전용이라 여기 안 쓴다.
  Widget _largeTitle(String text) => Padding(
        padding: const EdgeInsets.only(left: 4, top: 4, bottom: 18),
        child: Semantics(
          header: true,
          child: Text(
            text,
            style: const TextStyle(
              fontSize: 34,
              fontWeight: FontWeight.w800,
              height: 1.1,
              letterSpacing: -0.6,
              color: AppColors.foreground,
            ),
          ),
        ),
      );

  /// iOS 그룹 섹션 헤더 — 카드 밖 작은 muted 라벨. 카드 내부 제목과 층위가 다르다.
  Widget _sectionHeader(String text) => Padding(
        padding: const EdgeInsets.only(left: 4, top: 4, bottom: 10),
        child: Semantics(
          header: true,
          child: Text(
            text,
            style: const TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.2,
              color: AppColors.foregroundMuted,
            ),
          ),
        ),
      );

  // --- 1. 히어로 = 프로스티드 글라스. 거대 총 렙 수(브랜드 그라데이션) + 폼 점수 링(그라데이션 호).
  // 밝은 글라스 실효면(#FFF7F3) 위 텍스트는 어두운 잉크를 상속(GlassCard). 구간은 배경색이 아니라
  // 링 중앙 숫자 색(formScoreColor) + 아래 라벨/아이콘(band.accent)이 전달한다(WCAG 1.4.1). ---
  Widget _hero(
    BuildContext context,
    ({String label, IconData icon, Color accent}) band,
    num? totalReps,
    num? avgScore,
  ) {
    // 링 중앙 숫자 = 의미색(formScoreColor). 글라스 위 success 5.17 / secondary 4.74 / error 5.93:1.
    // 호(arc)도 같은 의미색 솔리드 — 트랙 대비 4.27~5.34:1로 1.4.11(3:1) 통과.
    final ringColor =
        avgScore == null ? AppColors.foregroundMuted : formScoreColor(avgScore);
    return GlassCard(
      padding: const EdgeInsets.fromLTRB(22, 20, 22, 22),
      radius: 26,
      semanticLabel: '${widget.exercise['name'] ?? ''} 운동 완료. '
          '총 렙 ${totalReps == null ? '없음' : '${_fmt(totalReps)}회'}, '
          '평균 폼 점수 ${avgScore == null ? '없음' : '${avgScore.round()}점'}, ${band.label}.',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.check_circle_rounded, size: 18, color: AppColors.foregroundMuted),
              SizedBox(width: 8),
              Text('운동 완료',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: AppColors.foregroundMuted)),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            widget.exercise['name'] as String? ?? '',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                height: 1.2,
                color: AppColors.foreground),
          ),
          const SizedBox(height: 20),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: BigStat(
                  style: AppBlocks.cream, // 글라스 위 라이트 톤(잉크 전경/뮤티드)
                  value: totalReps == null ? '-' : _fmt(totalReps),
                  unit: '회',
                  caption: '총 렙 수',
                  size: 58,
                  valueColor: AppColors.primary, // 히어로 숫자 = 솔리드 코랄(글라스 위 3.98:1)
                ),
              ),
              const SizedBox(width: 12),
              Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  FormScoreRing(
                    score: avgScore?.round(),
                    color: ringColor, // 채움 호 = 의미색 솔리드(트랙 대비 3:1↑)
                    size: 76,
                    strokeWidth: 9,
                  ),
                  const SizedBox(height: 6),
                  const Text('평균 폼 점수',
                      style: TextStyle(fontSize: 11, color: AppColors.foregroundMuted)),
                ],
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Icon(band.icon, size: 16, color: band.accent),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  band.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w700, color: band.accent),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // --- 2. 문장 분석(코치 노트) — 영상은 안 남고 점수만으론 자세가 안 고쳐진다. 남는 건 문장이다.
  // 백엔드 /sessions/{id}/analysis 의 good/bad/change/next/notes는 전부 list[str]다.
  // 이 블록만 별도 FutureBuilder로 감싼다 — 분석이 실패해도 아래 숫자·차트는 그대로 산다. ---
  Widget _analysisSection() {
    final future = _analysisFuture;
    if (future == null) {
      return _sentenceCard(
        style: AppBlocks.cream,
        outlined: true,
        icon: Icons.info_outline_rounded,
        title: '자세 분석',
        lines: const ['이 세션의 식별자가 없어 문장 분석을 불러올 수 없어요.'],
      );
    }
    return FutureBuilder<Map<String, dynamic>>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const BlockCard(
            style: AppBlocks.cream,
            outlined: true,
            child: Row(
              children: [
                SizedBox(
                    width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
                SizedBox(width: 14),
                Expanded(
                  child: Text('자세를 문장으로 분석하는 중…',
                      style: TextStyle(
                          fontSize: 14, height: 1.4, color: AppColors.foregroundMuted)),
                ),
              ],
            ),
          );
        }
        if (snapshot.hasError) {
          return ErrorCard(
            message: '자세 분석을 불러오지 못했습니다: ${snapshot.error}',
            onRetry: _retryAnalysis,
          );
        }

        final data = snapshot.data ?? const <String, dynamic>{};
        final next = _lines(data['next']);
        final good = _lines(data['good']);
        final bad = _lines(data['bad']);
        final change = _lines(data['change']);
        final notes = _lines(data['notes']);
        final comparedDate =
            (data['compared_with'] as Map<String, dynamic>?)?['date']?.toString();

        final cards = <Widget>[
          // iOS 톤 코치 노트 — 브랜드 3색으로 의미를 나눈다: 코랄(행동)·틸(잘함)·레드(고칠 점).
          // 색만으로 전달하지 않으려 카드마다 아이콘·제목을 병기한다(WCAG 1.4.1).
          if (next.isNotEmpty)
            _sentenceCard(
              // 다음에 할 것 = 가장 중요한 행동 지시 → 코랄 채움(미드 코랄)으로 시선을 잡는다.
              // 코랄 솔리드(gochujang)는 80점 히어로와 겹쳐 한 덩어리가 되므로 쓰지 않는다.
              style: AppBlocks.crimson,
              icon: Icons.flag_rounded,
              title: '다음에 할 것',
              lines: next,
            ),
          if (good.isNotEmpty)
            _sentenceCard(
              // 잘된 점 = 틸(성공). 페일 틸 색면 + 딥틸 전경 10.23:1.
              style: AppBlocks.tintCrimson,
              icon: Icons.check_circle_rounded,
              title: '잘된 점',
              lines: good,
            ),
          if (bad.isNotEmpty)
            _sentenceCard(
              // 고칠 점 = 레드(오류). iOS는 경고를 붉은 채움이 아니라 흰 셀 + 붉은 텍스트/아이콘으로 낸다.
              // error #BE123C on 흰 카드 = 6.29:1 (본문 4.5·그래픽 3:1 모두 충족). 본문은 짙은 전경.
              style: AppBlocks.cream,
              outlined: true,
              icon: Icons.warning_amber_rounded,
              accent: AppColors.error,
              title: '고칠 점',
              lines: bad,
            ),
          if (change.isNotEmpty)
            _sentenceCard(
              style: AppBlocks.tintNavy,
              icon: Icons.compare_arrows_rounded,
              title: '이전 대비 변화',
              // "어제 대비"로 뭉뚱그리지 않는다 — 실제 비교 대상 날짜를 적는다.
              subtitle: comparedDate == null ? null : '$comparedDate 세션과 비교',
              lines: change,
            ),
          // 관절 데이터 없음 / 첫 세션이라 비교 불가 등, 백엔드가 준 안내를 지어내지 않고 그대로 낸다.
          if (notes.isNotEmpty)
            _sentenceCard(
              style: AppBlocks.cream,
              outlined: true,
              icon: Icons.info_outline_rounded,
              title: '분석 참고',
              lines: notes,
            ),
        ];

        if (cards.isEmpty) {
          return const BlockCard(
            style: AppBlocks.cream,
            outlined: true,
            child: EmptyState(
              icon: Icons.notes_rounded,
              message: '이 세션에서 만들 수 있는 문장 분석이 없어요.',
              compact: true,
            ),
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (var i = 0; i < cards.length; i++) ...[
              if (i > 0) const SizedBox(height: 12),
              cards[i],
            ],
          ],
        );
      },
    );
  }

  static List<String> _lines(dynamic v) => ((v as List?) ?? const [])
      .map((e) => e.toString())
      .where((s) => s.trim().isNotEmpty)
      .toList();

  /// 긴 한국어 문장 전용 카드. 고정 높이를 주지 않는다 — 전부 Expanded + wrap으로 흐른다.
  Widget _sentenceCard({
    required BlockStyle style,
    required IconData icon,
    required String title,
    required List<String> lines,
    String? subtitle,
    Color? accent,
    bool outlined = false,
  }) {
    final showDots = lines.length > 1;
    // accent가 있으면 아이콘·제목을 같은 색으로 물들여 의미(예: 레드=고칠 점)를 헤더에 실어준다.
    // 본문 문장은 항상 style.foreground를 써서 긴 한국어가 최대 대비로 읽히게 둔다.
    final headColor = accent ?? style.foreground;
    return BlockCard(
      style: style,
      outlined: outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, size: 20, color: headColor),
              const SizedBox(width: 8),
              Expanded(
                child: Semantics(
                  header: true,
                  child: Text(title,
                      style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                          height: 1.25,
                          color: headColor)),
                ),
              ),
            ],
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 6),
            Text(subtitle, style: TextStyle(fontSize: 12, height: 1.4, color: style.mutedOr)),
          ],
          const SizedBox(height: 12),
          for (var i = 0; i < lines.length; i++) ...[
            if (i > 0) const SizedBox(height: 10),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (showDots) ...[
                  Container(
                    width: 6,
                    height: 6,
                    margin: const EdgeInsets.only(top: 7),
                    decoration: BoxDecoration(color: style.mutedOr, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 10),
                ],
                Expanded(
                  child: Text(lines[i], style: const TextStyle(fontSize: 14, height: 1.55)),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  // --- 3. 스탯 필 3연 — 서로 다른 색면. ---
  Widget _pillRow(List<Map<String, dynamic>> sets, List<num> reps) {
    final best = reps.isEmpty ? null : reps.reduce((a, b) => a > b ? a : b);
    final bestIndex = best == null ? -1 : reps.indexOf(best);
    final avgPerSet = reps.isEmpty
        ? null
        : reps.fold<num>(0, (a, b) => a + b) / reps.length;
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: StatPill(
              style: AppBlocks.gochujang,
              value: '${sets.length}',
              label: '세트',
              icon: Icons.layers_rounded,
              center: true,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: StatPill(
              style: AppBlocks.navy,
              value: best == null ? '-' : _fmt(best),
              unit: '회',
              label: best == null ? '최고 세트' : '최고 ${bestIndex + 1}세트',
              icon: Icons.trending_up_rounded,
              center: true,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: StatPill(
              // 솔리드 사이의 쉼표. 크림은 scaffold와 1.07:1이라 outlined 없으면 카드가 안 보인다.
              style: AppBlocks.cream,
              outlined: true,
              value: avgPerSet == null ? '-' : _fmt(avgPerSet),
              unit: '회',
              label: '세트 평균',
              icon: Icons.equalizer_rounded,
              center: true,
            ),
          ),
        ],
      ),
    );
  }

  // --- 4. 세트 기록 = 막대 차트 + 세트별 폼 점수 칩 (네이비 색면). ---
  Widget _setBlock(List<Map<String, dynamic>> sets, List<num> reps) {
    const s = AppBlocks.navy;
    if (sets.isEmpty) {
      return const BlockCard(
        style: s,
        child: EmptyState(
          icon: Icons.list_alt,
          message: '기록된 세트가 없습니다.',
          compact: true,
          dark: true,
        ),
      );
    }
    final labels = [for (var i = 1; i <= reps.length; i++) '$i'];
    final summary = [
      for (var i = 0; i < sets.length; i++)
        '${i + 1}세트 ${_fmt(reps[i])}회 ${_setScoreText(sets[i])}'
    ].join(', ');

    return BlockCard(
      style: s,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _blockTitle('세트 기록', trailing: '${sets.length}세트', style: s),
          const SizedBox(height: 16),
          MiniBarChart(
            values: reps,
            style: s,
            labels: labels,
            showValues: true,
            height: 110,
            semanticLabel: '세트별 렙 수. $summary',
          ),
          const SizedBox(height: 16),
          Container(height: 1, color: s.foreground.withValues(alpha: 0.15)),
          const SizedBox(height: 14),
          Text('세트별 폼 점수', style: TextStyle(fontSize: 12, color: s.mutedOr)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (var i = 0; i < sets.length; i++)
                _scoreChip(i, sets[i]['form_score'] as num?),
            ],
          ),
        ],
      ),
    );
  }

  /// 세트 하나의 점수 표기. 자세를 재지 않은 세트는 점수가 없다(0점이 아니다).
  static String _setScoreText(Map<String, dynamic> set) {
    final score = set['form_score'] as num?;
    return score == null ? '자세 측정 안 함' : '폼 ${score.round()}점';
  }

  /// 네이비 색면 = AppDark.scaffold와 동일 → formScoreColor(dark: true)가 검증된 조합 그대로 유효.
  /// 색 단독 전달 방지를 위해 아이콘(형태)과 숫자를 항상 병기한다.
  ///
  /// [score]가 null이면 그 세트는 영상 분석을 거치지 않아 점수가 없다. 0으로 그리면
  /// "자세가 엉망이었다"는 뜻이 되어버리므로 중립 색과 '—'로 구분해 표시한다.
  Widget _scoreChip(int index, num? score) {
    final c = score != null ? formScoreColor(score, dark: true) : AppBlocks.navy.mutedOr;
    return Semantics(
      label: score != null
          ? '${index + 1}세트 폼 점수 ${score.round()}점'
          : '${index + 1}세트 자세 측정 안 함',
      child: ExcludeSemantics(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            // 0.6은 저점수(error #F2737C)일 때만 네이비 위 2.53:1로 3:1 미달이었다.
            // 0.75면 3.30:1로 세 구간 모두 통과한다.
            border: Border.all(color: c.withValues(alpha: 0.75)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(score != null ? formScoreIcon(score) : Icons.remove_rounded, size: 14, color: c),
              const SizedBox(width: 5),
              Text('${index + 1}세트',
                  style: TextStyle(fontSize: 12, color: AppBlocks.navy.mutedOr)),
              const SizedBox(width: 6),
              Text(score != null ? '${score.round()}' : '—',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                      color: c,
                      fontFeatures: const [FontFeature.tabularFigures()])),
            ],
          ),
        ),
      ),
    );
  }

  // --- 5. 오늘 vs 이전 — 버려지던 sets[]를 PairedBarChart로 (고추장 색면). ---
  Widget _compareBlock() {
    const s = AppBlocks.gochujang;
    return FutureBuilder<Map<String, dynamic>>(
      future: _compareFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const BlockCard(
            style: s,
            child: SizedBox(
              height: 200,
              child: Center(
                child: CircularProgressIndicator(color: AppColors.onPrimary),
              ),
            ),
          );
        }
        if (snapshot.hasError) {
          return ErrorCard(
            message: '비교 데이터를 불러오지 못했습니다: ${snapshot.error}',
            onRetry: _retryCompare,
          );
        }
        final data = snapshot.data ?? {};
        final today = data['today'];
        final previous = data['previous'];
        if (today == null || previous == null) {
          // EmptyState(dark:)는 네이비 전용 muted를 쓴다 → 고추장 색면에선 검증된 s.mutedOr로 직접 조립.
          return BlockCard(
            style: s,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Column(
                children: [
                  Icon(Icons.compare_arrows, size: 28, color: s.mutedOr),
                  const SizedBox(height: 10),
                  Text('비교할 이전 기록이 없습니다',
                      style: TextStyle(fontSize: 13, color: s.mutedOr)),
                ],
              ),
            ),
          );
        }
        final todayReps = _reps(_setsOf(today));
        final prevReps = _reps(_setsOf(previous));
        final prevDate = (previous as Map<String, dynamic>)['date']?.toString();
        final prevLabel = prevDate == null ? '이전' : '이전 ($prevDate)';
        final delta = data['delta'] as Map<String, dynamic>? ?? {};

        return BlockCard(
          style: s,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _blockTitle('오늘 vs 이전', trailing: prevDate, style: s),
              const SizedBox(height: 16),
              PairedBarChart(
                current: todayReps,
                previous: prevReps,
                style: s,
                currentLabel: '오늘',
                previousLabel: prevLabel,
                height: 120,
                semanticLabel: '세트별 렙 수 비교. 오늘 '
                    '${todayReps.map(_fmt).join(', ')}회. '
                    '$prevLabel ${prevReps.map(_fmt).join(', ')}회.',
              ),
              const SizedBox(height: 18),
              Container(height: 1, color: s.foreground.withValues(alpha: 0.18)),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(child: _delta(s, '총 렙 수', delta['total_reps'] as num?)),
                  const SizedBox(width: 12),
                  Expanded(child: _delta(s, '평균 폼 점수', delta['avg_form_score'] as num?)),
                  // ponytail: 운동량 행 제외 — 지표 정의(Q11) 확정 후 백엔드 delta.volume 추가와 함께 복원
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  /// 증감을 화살표 **방향**으로 전달한다 — 솔리드 색면 위에서 success/error 색은 대비가 죽는다.
  Widget _delta(BlockStyle s, String label, num? v) {
    final IconData icon;
    final String text;
    final String direction;
    if (v == null || v == 0) {
      icon = Icons.remove_rounded;
      text = '0';
      direction = '변화 없음';
    } else if (v > 0) {
      icon = Icons.arrow_upward_rounded;
      text = '+${_fmt(v)}';
      direction = '${_fmt(v)} 증가';
    } else {
      icon = Icons.arrow_downward_rounded;
      text = '−${_fmt(v.abs())}';
      direction = '${_fmt(v.abs())} 감소';
    }
    return Semantics(
      label: '$label $direction',
      child: ExcludeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 12, color: s.mutedOr)),
            const SizedBox(height: 4),
            Row(
              children: [
                Icon(icon, size: 18, color: s.foreground),
                const SizedBox(width: 4),
                Flexible(
                  child: Text(text,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                          fontFeatures: [FontFeature.tabularFigures()])),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  // --- 6. 폼 점수 추이 — 스파크라인은 라이트 배경 전용 색을 쓰므로 크림 색면 위에 올린다. ---
  Widget _trendBlock() {
    const s = AppBlocks.cream;
    return FutureBuilder<List<num>>(
      future: _recentScoresFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const BlockCard(
            style: s,
            outlined: true,
            child: SizedBox(height: 110, child: Center(child: CircularProgressIndicator())),
          );
        }
        if (snapshot.hasError) {
          return ErrorCard(
            message: '추이 데이터를 불러오지 못했습니다: ${snapshot.error}',
            onRetry: _retryRecentScores,
          );
        }
        final scores = snapshot.data ?? [];
        if (scores.length < 2) {
          return const BlockCard(
            style: s,
            outlined: true,
            child: EmptyState(
              icon: Icons.show_chart,
              message: '추이를 보려면 기록이 더 필요해요.',
              compact: true,
            ),
          );
        }
        return BlockCard(
          style: s,
          outlined: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _blockTitle('최근 폼 점수 추이',
                  trailing: '최근 ${scores.length}회', style: s),
              const SizedBox(height: 16),
              FormScoreSparkline(scores: scores),
            ],
          ),
        );
      },
    );
  }

  Widget _blockTitle(String title, {String? trailing, required BlockStyle style}) {
    return Row(
      children: [
        Expanded(
          child: Text(title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
        ),
        if (trailing != null)
          Text(trailing, style: TextStyle(fontSize: 12, color: style.mutedOr)),
      ],
    );
  }
}
