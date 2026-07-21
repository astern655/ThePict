import 'package:flutter/material.dart';
import '../api.dart';
import '../main.dart';
import '../widgets/common.dart';
import 'root.dart';

/// 폼 점수 구간 → 히어로 색면 + 구간 라벨.
/// 색만으로 구간을 전달하지 않으려고 라벨/아이콘을 항상 함께 반환한다 (WCAG 1.4.1).
({BlockStyle style, String label, IconData icon}) _scoreBand(num? score) {
  if (score == null) {
    return (style: AppBlocks.navy, label: '점수 없음', icon: Icons.remove_rounded);
  }
  if (score >= 80) {
    return (style: AppBlocks.gochujang, label: '우수한 자세', icon: formScoreIcon(score));
  }
  if (score >= 60) {
    return (style: AppBlocks.navy, label: '무난한 자세', icon: formScoreIcon(score));
  }
  return (style: AppBlocks.crimson, label: '자세 개선 필요', icon: formScoreIcon(score));
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

    return Scaffold(
      appBar: AppBar(title: const Text('세션 요약')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          _hero(context, band, totalReps, avgScore),
          const SizedBox(height: 20),
          // 점수 바로 아래가 문장 자리다 — "82점"이 무슨 뜻인지는 여기서만 알 수 있다.
          Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 10),
            child: Semantics(
              header: true,
              child: const Text(
                '코치 노트',
                style: TextStyle(
                    fontSize: 15, fontWeight: FontWeight.w700, color: AppColors.foregroundMuted),
              ),
            ),
          ),
          _analysisSection(),
          const SizedBox(height: 20),
          _pillRow(sets, reps),
          const SizedBox(height: 12),
          _setBlock(sets, reps),
          const SizedBox(height: 12),
          _compareBlock(),
          const SizedBox(height: 12),
          _trendBlock(),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: () => Navigator.of(context).pushAndRemoveUntil(
              fadeRoute(context, (_) => const RootScreen()),
              (route) => false,
            ),
            child: const Text('홈으로'),
          ),
        ],
      ),
    );
  }

  // --- 1. 히어로 색면: 거대 총 렙 수 + 폼 점수 링. 카드 배경색이 점수 구간을 말한다. ---
  Widget _hero(
    BuildContext context,
    ({BlockStyle style, String label, IconData icon}) band,
    num? totalReps,
    num? avgScore,
  ) {
    final s = band.style;
    return BlockCard(
      style: s,
      padding: const EdgeInsets.fromLTRB(22, 20, 22, 22),
      radius: 26,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.check_circle_rounded, size: 18, color: s.mutedOr),
              const SizedBox(width: 8),
              Text('운동 완료',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: s.mutedOr)),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            widget.exercise['name'] as String? ?? '',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, height: 1.2),
          ),
          const SizedBox(height: 20),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: BigStat(
                  style: s,
                  value: totalReps == null ? '-' : _fmt(totalReps),
                  unit: '회',
                  caption: '총 렙 수',
                  size: 64,
                ),
              ),
              const SizedBox(width: 12),
              Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  FormScoreRing(
                    score: avgScore?.round(),
                    // 솔리드 색면 위에서는 formScoreColor 계열이 대비를 못 맞춘다 → 전경색 링.
                    // 구간 정보는 카드 배경색 + 아래 라벨/아이콘이 담당한다.
                    color: s.foreground,
                    // 트랙 alpha 0.22는 색면에 녹아 링이 끊긴 호처럼 보였다
                    // (crimson 1.34:1, gochujang 1.57:1, navy 1.86:1 — 전부 1.4.11의 3:1 미달).
                    // 0.7이면 navy 6.77 / crimson 3.27 / gochujang 5.50으로 셋 다 통과하고,
                    // 채움(100%)과는 여전히 30% 차이가 남아 게이지 비율이 읽힌다.
                    // mutedOr는 crimson에서 foreground로 폴백돼 채움과 같은 색이 되므로 쓰지 않는다.
                    trackColor: s.foreground.withValues(alpha: 0.7),
                    size: 76,
                    strokeWidth: 9,
                  ),
                  const SizedBox(height: 6),
                  Text('평균 폼 점수', style: TextStyle(fontSize: 11, color: s.mutedOr)),
                ],
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Icon(band.icon, size: 16, color: s.foreground),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  band.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
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
          // 네 카드의 배경 휘도를 우선순위 순으로 내린다(0.123 → 0.056 → 0.028 → 0.014).
          // 행동 지시가 이 묶음에서 가장 밝다. 라임 솔리드(gochujang)는 쓰지 않는다 —
          // 80점 이상이면 히어로가 라임이라, 여기까지 라임이면 두 카드가 한 덩어리로 붙는다.
          if (next.isNotEmpty)
            _sentenceCard(
              style: AppBlocks.crimson,
              icon: Icons.flag_rounded,
              title: '다음에 할 것',
              lines: next,
            ),
          if (good.isNotEmpty)
            _sentenceCard(
              style: AppBlocks.tintGochujang,
              icon: Icons.check_circle_rounded,
              title: '잘된 점',
              lines: good,
            ),
          if (bad.isNotEmpty)
            _sentenceCard(
              // 유일하게 그린 램프 밖의 중립 다크 패널 — 톤이 반대라는 걸 색면으로도 말한다.
              style: AppBlocks.navy,
              icon: Icons.warning_amber_rounded,
              // #F87171 on #272E2A = 4.89:1 (1.4.11의 3:1, 본문 4.5:1 둘 다 충족).
              iconColor: AppColors.error,
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
    Color? iconColor,
    bool outlined = false,
  }) {
    final showDots = lines.length > 1;
    return BlockCard(
      style: style,
      outlined: outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, size: 20, color: iconColor ?? style.foreground),
              const SizedBox(width: 8),
              Expanded(
                child: Semantics(
                  header: true,
                  child: Text(title,
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w800, height: 1.25)),
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
        '${i + 1}세트 ${_fmt(reps[i])}회 폼 ${((sets[i]['form_score'] as num?) ?? 0).round()}점'
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
                _scoreChip(i, (sets[i]['form_score'] as num?) ?? 0),
            ],
          ),
        ],
      ),
    );
  }

  /// 네이비 색면 = AppDark.scaffold와 동일 → formScoreColor(dark: true)가 검증된 조합 그대로 유효.
  /// 색 단독 전달 방지를 위해 아이콘(형태)과 숫자를 항상 병기한다.
  Widget _scoreChip(int index, num score) {
    final c = formScoreColor(score, dark: true);
    return Semantics(
      label: '${index + 1}세트 폼 점수 ${score.round()}점',
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
              Icon(formScoreIcon(score), size: 14, color: c),
              const SizedBox(width: 5),
              Text('${index + 1}세트',
                  style: TextStyle(fontSize: 12, color: AppBlocks.navy.mutedOr)),
              const SizedBox(width: 6),
              Text('${score.round()}',
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
