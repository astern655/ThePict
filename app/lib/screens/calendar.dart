import 'package:flutter/material.dart';
import '../api.dart';
import '../main.dart';
import '../widgets/common.dart';

class CalendarScreen extends StatefulWidget {
  const CalendarScreen({super.key});

  @override
  State<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarData {
  /// `/calendar`가 준 "기록 있는 날" 집합.
  final Set<String> markedDates;

  /// 날짜별 세션 개수 — 히트맵 농도의 원천(`/calendar`는 있음/없음만 준다).
  final Map<String, int> countByDate;

  final int sessionCount;
  final int totalReps;
  final double? avgForm;

  /// 주차별 세션 수(1주 = 1~7일). 히어로 카드 막대그래프용.
  final List<int> weekly;

  const _CalendarData({
    required this.markedDates,
    required this.countByDate,
    required this.sessionCount,
    required this.totalReps,
    required this.avgForm,
    required this.weekly,
  });
}

/// 큰 수를 필/배지 폭에 맞게 줄인다 (1240 → 1.2k). 색면 배지는 폭이 좁아 원문이 잘린다.
String _compact(num v) {
  if (v < 1000) return v is int ? '$v' : v.toStringAsFixed(0);
  if (v < 10000) return '${(v / 1000).toStringAsFixed(1)}k';
  return '${(v / 1000).round()}k';
}

/// 세션 개수 → 색면 농도. 0=중립, 1=옅은 틴트, 2=크림슨, 3+=고추장.
/// 색만으로 전달하지 않는다 — 셀에 개수 숫자를 같이 찍는다(WCAG 1.4.1).
BlockStyle _heatStyle(int count) {
  if (count <= 0) return AppBlocks.cream;
  if (count == 1) return AppBlocks.tintGochujang;
  if (count == 2) return AppBlocks.crimson;
  return AppBlocks.gochujang;
}

class _CalendarScreenState extends State<CalendarScreen> {
  DateTime _month = DateTime(DateTime.now().year, DateTime.now().month);
  late Future<_CalendarData> _dataFuture;

  /// exercise_id → 표시 이름. 바텀시트가 원문 ID를 노출하지 않도록 조인용으로 보관.
  Map<String, String> _exerciseNames = const {};

  String get _monthKey =>
      '${_month.year.toString().padLeft(4, '0')}-${_month.month.toString().padLeft(2, '0')}';

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    final monthKey = _monthKey;
    _dataFuture = Future.wait([
      Api.instance.getCalendar(monthKey),
      Api.instance.getSessions(),
      Api.instance.getExercises(),
    ]).then((results) {
      final marked = ((results[0] as Map<String, dynamic>)['dates'] as List? ?? [])
          .map((d) => d.toString())
          .toSet();

      final monthSessions = (results[1] as List)
          .cast<Map<String, dynamic>>()
          .where((s) => s['date'].toString().startsWith(monthKey))
          .toList();

      final countByDate = <String, int>{};
      final weekly = List<int>.filled(6, 0);
      var totalReps = 0;
      var formSum = 0.0;
      var formCount = 0;
      for (final s in monthSessions) {
        final date = s['date'].toString();
        countByDate[date] = (countByDate[date] ?? 0) + 1;
        final day = int.tryParse(date.split('-').last) ?? 1;
        weekly[((day - 1) ~/ 7).clamp(0, 5)] += 1;
        totalReps += (s['total_reps'] as num?)?.toInt() ?? 0;
        final f = s['avg_form_score'] as num?;
        if (f != null) {
          formSum += f.toDouble();
          formCount += 1;
        }
      }

      _exerciseNames = {
        for (final e in (results[2] as List).cast<Map<String, dynamic>>())
          e['id'].toString(): (e['name'] ?? e['id']).toString(),
      };

      final daysInMonth = DateTime(_month.year, _month.month + 1, 0).day;
      final weekCount = ((daysInMonth - 1) ~/ 7) + 1;

      return _CalendarData(
        markedDates: marked,
        countByDate: countByDate,
        sessionCount: monthSessions.length,
        totalReps: totalReps,
        avgForm: formCount == 0 ? null : formSum / formCount,
        weekly: weekly.sublist(0, weekCount),
      );
    });
  }

  void _changeMonth(int delta) {
    setState(() {
      _month = DateTime(_month.year, _month.month + delta);
      _load();
    });
  }

  /// 날짜 탭 → 그날의 세션 **+ 분석**을 담은 시트.
  /// `/analysis`(getDayAnalysis) 한 번이면 세션 목록과 세션별 분석이 함께 온다 —
  /// 기존 `getSessions(date)` 호출은 이 응답의 `sessions`에 그대로 포함되므로 대체했다.
  /// 시트를 먼저 띄우고 안에서 로딩/에러/빈 상태를 처리한다(탭 후 무반응 구간 제거).
  void _showDay(String dateStr) {
    final day = DateTime.tryParse(dateStr);
    showModalBottomSheet(
      context: context,
      // 분석 문장이 길어 시트가 화면 절반을 넘는다 → 드래그로 높이를 사용자가 정한다.
      isScrollControlled: true,
      // 시트 전체가 하나의 중립 다크 색면 — 화면에서 올라오는 순간 면이 바뀐다.
      backgroundColor: AppBlocks.navy.background,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
      ),
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.72,
        minChildSize: 0.4,
        maxChildSize: 0.95,
        builder: (context, scrollController) => _DaySheet(
          date: dateStr,
          title: day == null ? dateStr : '${day.month}월 ${day.day}일',
          exerciseNames: _exerciseNames,
          scrollController: scrollController,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('$_monthKey 기록'),
        actions: [
          IconButton(
              tooltip: '이전 달',
              icon: const Icon(Icons.chevron_left),
              onPressed: () => _changeMonth(-1)),
          IconButton(
              tooltip: '다음 달',
              icon: const Icon(Icons.chevron_right),
              onPressed: () => _changeMonth(1)),
        ],
      ),
      body: FutureBuilder<_CalendarData>(
        future: _dataFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: ErrorCard(
                  message: '불러오기 실패: ${snapshot.error}',
                  onRetry: () => setState(_load),
                ),
              ),
            );
          }
          final data = snapshot.data!;
          return ListView(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
            children: [
              _MonthHero(month: _month, data: data),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: StatPill(
                      style: AppBlocks.crimson,
                      value: '${data.markedDates.length}',
                      unit: '일',
                      label: '운동일 수',
                      icon: Icons.calendar_month_rounded,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: StatPill(
                      style: AppBlocks.gochujang,
                      value: '${data.sessionCount}',
                      unit: '회',
                      label: '총 세션',
                      icon: Icons.repeat_rounded,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: StatPill(
                      style: AppBlocks.cream,
                      outlined: true, // 크림 필은 크림 scaffold 위 1.07:1 — 경계가 없으면 사라진다
                      value: data.avgForm == null ? '–' : '${data.avgForm!.round()}',
                      unit: data.avgForm == null ? null : '점',
                      label: '평균 폼 점수',
                      icon: Icons.speed_rounded,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              _MonthGrid(
                month: _month,
                countByDate: data.countByDate,
                markedDates: data.markedDates,
                onTapDay: _showDay,
              ),
              const SizedBox(height: 12),
              const _HeatLegend(),
              if (data.markedDates.isEmpty) ...[
                const SizedBox(height: 8),
                const EmptyState(
                  icon: Icons.calendar_month_outlined,
                  message: '이 달에는 기록이 없어요.',
                  compact: true,
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

/// 월 히어로 — 네이비 솔리드 색면. 거대 숫자(총 렙) + 주차별 세션 막대.
class _MonthHero extends StatelessWidget {
  final DateTime month;
  final _CalendarData data;
  const _MonthHero({required this.month, required this.data});

  @override
  Widget build(BuildContext context) {
    const style = AppBlocks.navy;
    return BlockCard(
      style: style,
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 18),
      semanticLabel: '${month.month}월 총 ${data.totalReps}렙, '
          '운동일 ${data.markedDates.length}일, 세션 ${data.sessionCount}회',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${month.month}월 누적',
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: style.mutedOr)),
          const SizedBox(height: 10),
          BigStat(
            style: style,
            value: _compact(data.totalReps),
            unit: '렙',
            caption: data.sessionCount == 0 ? '아직 기록이 없어요' : '${data.sessionCount}회 세션의 합계',
            size: 52,
          ),
          const SizedBox(height: 16),
          MiniBarChart(
            values: data.weekly,
            style: style,
            labels: [for (var i = 1; i <= data.weekly.length; i++) '$i주'],
            showValues: true,
            height: 90,
            semanticLabel: '주차별 세션 수 ${data.weekly.join(", ")}',
          ),
        ],
      ),
    );
  }
}

/// 날짜 그리드 — 크림 색면 위에 세션 수 농도 히트맵.
class _MonthGrid extends StatelessWidget {
  final DateTime month;
  final Map<String, int> countByDate;
  final Set<String> markedDates;
  final ValueChanged<String> onTapDay;

  const _MonthGrid({
    required this.month,
    required this.countByDate,
    required this.markedDates,
    required this.onTapDay,
  });

  @override
  Widget build(BuildContext context) {
    final firstDay = DateTime(month.year, month.month, 1);
    final daysInMonth = DateTime(month.year, month.month + 1, 0).day;
    final leadingBlanks = firstDay.weekday % 7; // 일요일=0 시작
    final cellCount = leadingBlanks + daysInMonth;
    final now = DateTime.now();

    return BlockCard(
      style: AppBlocks.cream,
      outlined: true, // 크림 scaffold 위 1.07:1 — 그리드 카드 경계를 살린다
      padding: const EdgeInsets.fromLTRB(6, 12, 6, 10),
      child: Column(
        children: [
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 4),
            child: _WeekdayHeader(),
          ),
          const SizedBox(height: 6),
          LayoutBuilder(
            builder: (context, constraints) {
              // 칸 높이를 52dp로 고정 — 7열 캘린더는 폭이 화면에 묶이므로 세로로 터치 타깃을 확보한다.
              final cellWidth = constraints.maxWidth / 7;
              return GridView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                padding: EdgeInsets.zero,
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 7,
                  // 간격은 0 — 셀 사이 여백은 셀 내부 패딩으로 만들어 탭 영역을 슬롯 전체로 유지한다.
                  childAspectRatio: cellWidth / 52,
                ),
                itemCount: cellCount,
                itemBuilder: (context, index) {
                  if (index < leadingBlanks) return const SizedBox.shrink();
                  final day = index - leadingBlanks + 1;
                  final dateStr =
                      '${month.year.toString().padLeft(4, '0')}-${month.month.toString().padLeft(2, '0')}-${day.toString().padLeft(2, '0')}';
                  final count =
                      countByDate[dateStr] ?? (markedDates.contains(dateStr) ? 1 : 0);
                  final style = _heatStyle(count);
                  final isToday =
                      now.year == month.year && now.month == month.month && now.day == day;

                  return Semantics(
                    button: true,
                    label: '${month.month}월 $day일'
                        '${count == 0 ? ', 기록 없음' : ', 세션 $count회'}'
                        '${isToday ? ', 오늘' : ''}',
                    excludeSemantics: true,
                    child: InkWell(
                      onTap: () => onTapDay(dateStr),
                      borderRadius: BorderRadius.circular(12),
                      child: Padding(
                        padding: const EdgeInsets.all(2),
                        child: Container(
                          decoration: BoxDecoration(
                            color: style.background,
                            borderRadius: BorderRadius.circular(12),
                            // '오늘' 링을 네이비 고정색으로 두면 진한 히트 셀에서 사라진다
                            // (크림슨 위 2.24:1, 고추장 위 1.20:1). 셀 자신의 전경색을 쓰면
                            // 옅은 셀에선 네이비, 진한 셀에선 크림이 되어 어느 농도에서도 보인다.
                            border: Border.all(
                              color: isToday
                                  ? style.foreground
                                  : (count == 0 ? AppColors.border : Colors.transparent),
                              width: isToday ? 2 : 1,
                            ),
                          ),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text('$day',
                                  style: TextStyle(
                                    fontWeight: count > 0 ? FontWeight.w800 : FontWeight.w500,
                                    fontSize: 14,
                                    color: style.foreground,
                                    fontFeatures: const [FontFeature.tabularFigures()],
                                  )),
                              // 색 농도와 별개의 신호 — 세션 수를 숫자로 병기한다.
                              SizedBox(
                                height: 13,
                                child: count > 0
                                    ? Text('×$count',
                                        style: TextStyle(
                                          fontSize: 10,
                                          fontWeight: FontWeight.w700,
                                          color: style.mutedOr,
                                        ))
                                    : null,
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  );
                },
              );
            },
          ),
        ],
      ),
    );
  }
}

/// 히트맵 농도 범례 — 색 농도가 무엇을 뜻하는지 글자로 못 박는다.
class _HeatLegend extends StatelessWidget {
  const _HeatLegend();

  @override
  Widget build(BuildContext context) {
    const items = [
      (0, '없음'),
      (1, '1회'),
      (2, '2회'),
      (3, '3회+'),
    ];
    return Semantics(
      label: '색 농도 범례: 옅을수록 세션이 적고 진할수록 많습니다. 칸 안 숫자로도 표시됩니다.',
      excludeSemantics: true,
      child: Wrap(
        spacing: 14,
        runSpacing: 6,
        children: [
          for (final (count, label) in items)
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 14,
                  height: 14,
                  decoration: BoxDecoration(
                    color: _heatStyle(count).background,
                    borderRadius: BorderRadius.circular(4),
                    border: count == 0 ? Border.all(color: AppColors.border) : null,
                  ),
                ),
                const SizedBox(width: 5),
                Text(label,
                    style: const TextStyle(fontSize: 11, color: AppColors.foregroundMuted)),
              ],
            ),
        ],
      ),
    );
  }
}

/// 날짜 시트 — 그날 요약 + 세션별 기록/분석.
///
/// 세션이 여러 개면 전부 펼친 채로 두면 문장이 수십 줄이 되어 스크롤이 미아가 된다.
/// 그래서 **세션 1개면 자동으로 펼치고, 2개 이상이면 전부 접은 채 시작**한다.
/// 접힌 상태에서도 운동 이름·렙·점수는 보이므로 무엇을 펼칠지 판단할 수 있다.
class _DaySheet extends StatefulWidget {
  final String date;
  final String title;
  final Map<String, String> exerciseNames;
  final ScrollController scrollController;

  const _DaySheet({
    required this.date,
    required this.title,
    required this.exerciseNames,
    required this.scrollController,
  });

  @override
  State<_DaySheet> createState() => _DaySheetState();
}

class _DaySheetState extends State<_DaySheet> {
  late Future<Map<String, dynamic>> _future = Api.instance.getDayAnalysis(widget.date);
  final _expanded = <String>{};
  bool _seeded = false;

  void _reload() {
    setState(() {
      _seeded = false;
      _expanded.clear();
      _future = Api.instance.getDayAnalysis(widget.date);
    });
  }

  @override
  Widget build(BuildContext context) {
    const sheet = AppBlocks.navy;
    return SafeArea(
      top: false,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 12),
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: sheet.mutedOr,
                borderRadius: BorderRadius.circular(999),
              ),
            ),
          ),
          const SizedBox(height: 14),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              widget.title,
              style: TextStyle(
                color: sheet.foreground,
                fontSize: 22,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          const SizedBox(height: 12),
          Expanded(
            child: FutureBuilder<Map<String, dynamic>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Padding(
                    padding: EdgeInsets.fromLTRB(16, 0, 16, 24),
                    child: SkeletonList(itemCount: 2),
                  );
                }
                if (snapshot.hasError) {
                  return SingleChildScrollView(
                    controller: widget.scrollController,
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
                    child: ErrorCard(
                      message: '분석을 불러오지 못했습니다: ${snapshot.error}',
                      onRetry: _reload,
                    ),
                  );
                }

                final data = snapshot.data ?? const <String, dynamic>{};
                final summary = (data['summary'] as List? ?? const [])
                    .map((e) => e.toString())
                    .toList();
                final sessions =
                    (data['sessions'] as List? ?? const []).cast<Map<String, dynamic>>();

                // 세션 1개짜리 날은 접어둘 이유가 없다 — 한 번만 초기 펼침을 심는다.
                if (!_seeded) {
                  _seeded = true;
                  if (sessions.length == 1) _expanded.add(sessions.first['id'].toString());
                }

                return ListView(
                  controller: widget.scrollController,
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
                  children: [
                    if (summary.isNotEmpty) _summaryCard(summary, sessions.length),
                    if (sessions.isEmpty)
                      const EmptyState(
                        icon: Icons.event_note,
                        message: '이 날의 기록이 없습니다.',
                        compact: true,
                      )
                    else
                      ...sessions.map((s) {
                        final id = s['id'].toString();
                        return Padding(
                          padding: const EdgeInsets.only(top: 10),
                          child: _SessionAnalysisCard(
                            session: s,
                            exerciseName: widget.exerciseNames[s['exercise_id'].toString()] ??
                                s['exercise_id'].toString(),
                            expanded: _expanded.contains(id),
                            onToggle: () => setState(
                              () => _expanded.contains(id) ? _expanded.remove(id) : _expanded.add(id),
                            ),
                          ),
                        );
                      }),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  /// 그날 전체 요약 — 시트 맨 위 딤 그린 색면.
  /// 시트 배경(#272E2A) 대비 1.40:1이라 `outlined`가 없으면 면이 사라진다(경계 5.54:1).
  Widget _summaryCard(List<String> summary, int sessionCount) {
    const style = AppBlocks.tintGochujang;
    return BlockCard(
      style: style,
      outlined: true,
      padding: const EdgeInsets.all(16),
      semanticLabel: '이 날의 요약. ${summary.join(" ")}',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.insights_rounded, size: 18, color: AppColors.primary),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  '이 날의 요약',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: AppColors.primary,
                  ),
                ),
              ),
              Text('세션 $sessionCount회',
                  style: TextStyle(fontSize: 12, color: style.mutedOr)),
            ],
          ),
          const SizedBox(height: 8),
          for (final line in summary)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(line,
                  style: TextStyle(fontSize: 14, height: 1.5, color: style.foreground)),
            ),
        ],
      ),
    );
  }
}

/// 세션 하나 — 접힌 상태는 헤더(운동·렙·점수)만, 펼치면 세트 막대 + 분석 문장.
class _SessionAnalysisCard extends StatelessWidget {
  final Map<String, dynamic> session;
  final String exerciseName;
  final bool expanded;
  final VoidCallback onToggle;

  const _SessionAnalysisCard({
    required this.session,
    required this.exerciseName,
    required this.expanded,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    const style = AppBlocks.cream;
    final reps = (session['total_reps'] as num?)?.toInt() ?? 0;
    final score = session['avg_form_score'] as num?;
    final sets = (session['sets'] as List? ?? const []).cast<Map<String, dynamic>>();
    final setReps = sets.map((e) => (e['reps'] as num?) ?? 0).toList();
    final analysis = (session['analysis'] as Map?)?.cast<String, dynamic>();

    return BlockCard(
      style: style,
      // 시트 배경(#272E2A) 대비 1.26:1 — 경계 없이는 카드가 배경에 녹는다(경계 4.41:1).
      outlined: true,
      padding: const EdgeInsets.fromLTRB(6, 6, 6, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            button: true,
            expanded: expanded,
            label: '$exerciseName, 총 $reps렙'
                '${score == null ? '' : ', 평균 폼 점수 ${score.round()}점'}'
                ', 세트 ${sets.length}개. ${expanded ? '접기' : '분석 펼치기'}',
            excludeSemantics: true,
            child: InkWell(
              onTap: onToggle,
              borderRadius: BorderRadius.circular(16),
              child: Container(
                constraints: const BoxConstraints(minHeight: 48),
                padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
                child: Row(
                  children: [
                    Icon(Icons.fitness_center, size: 18, color: style.foreground),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(exerciseName,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w800,
                                  color: style.foreground)),
                          const SizedBox(height: 2),
                          Text('총 $reps렙 · 세트 ${sets.length}개',
                              style: TextStyle(fontSize: 12, color: style.mutedOr)),
                        ],
                      ),
                    ),
                    if (score != null) ...[
                      const SizedBox(width: 6),
                      Icon(formScoreIcon(score), size: 16, color: formScoreColor(score)),
                      const SizedBox(width: 4),
                      Text('${score.round()}점',
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                            color: formScoreColor(score),
                          )),
                    ],
                    Icon(expanded ? Icons.expand_less_rounded : Icons.expand_more_rounded,
                        color: style.mutedOr),
                  ],
                ),
              ),
            ),
          ),
          if (expanded)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 2, 12, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (setReps.length > 1) ...[
                    MiniBarChart(
                      values: setReps,
                      style: style,
                      labels: [for (var i = 1; i <= setReps.length; i++) '$i'],
                      showValues: true,
                      height: 84,
                      semanticLabel: '세트별 렙 수 ${setReps.map((v) => v.toString()).join(", ")}',
                    ),
                    const SizedBox(height: 14),
                  ],
                  if (analysis == null)
                    Text('이 세션의 분석을 만들지 못했어요.',
                        style: TextStyle(fontSize: 13, color: style.mutedOr))
                  else
                    ..._analysisSections(analysis),
                ],
              ),
            ),
        ],
      ),
    );
  }

  List<Widget> _analysisSections(Map<String, dynamic> a) {
    List<String> lines(String key) =>
        (a[key] as List? ?? const []).map((e) => e.toString()).toList();

    final compared = (a['compared_with'] as Map?)?.cast<String, dynamic>();
    final changeTitle =
        compared == null ? '지난 세션과 비교' : '지난 세션(${compared['date']})과 비교';

    // 색은 보조 신호일 뿐 — 모든 구획에 아이콘과 한국어 제목이 함께 붙는다(WCAG 1.4.1).
    final sections = <_AnalysisBlock>[
      // 가장 행동 가능한 정보를 맨 위로. 나머지는 근거다.
      _AnalysisBlock(
        lines: lines('next'),
        title: '이렇게 고쳐보세요',
        icon: Icons.flag_rounded,
        highlighted: true,
      ),
      _AnalysisBlock(
        lines: lines('bad'),
        title: '아쉬웠던 점',
        icon: Icons.warning_amber_rounded,
        color: AppColors.error, // 카드면 위 6.36:1
      ),
      _AnalysisBlock(
        lines: lines('good'),
        title: '잘한 점',
        icon: Icons.check_circle_rounded,
        color: AppColors.success, // 11.66:1
      ),
      _AnalysisBlock(
        lines: lines('change'),
        title: changeTitle,
        icon: Icons.timeline_rounded,
        color: AppColors.secondary, // 10.53:1
      ),
      _AnalysisBlock(
        lines: lines('notes'),
        title: '참고',
        icon: Icons.info_outline_rounded,
        color: AppColors.foregroundMuted, // 7.25:1
      ),
    ];

    final visible = sections.where((b) => b.lines.isNotEmpty).toList();
    if (visible.isEmpty) {
      return [
        Text('이 세션에서는 분석할 문장이 없어요.',
            style: TextStyle(fontSize: 13, color: AppBlocks.cream.mutedOr)),
      ];
    }
    return visible;
  }
}

/// 분석 문장 한 묶음. 한국어 장문이 들어오므로 고정 높이 없이 흐르게 둔다.
class _AnalysisBlock extends StatelessWidget {
  final List<String> lines;
  final String title;
  final IconData icon;
  final Color? color;

  /// 교정 지시처럼 최우선 항목은 별도 색면으로 띄운다.
  final bool highlighted;

  const _AnalysisBlock({
    required this.lines,
    required this.title,
    required this.icon,
    this.color,
    this.highlighted = false,
  });

  @override
  Widget build(BuildContext context) {
    final style = highlighted ? AppBlocks.tintGochujang : AppBlocks.cream;
    final accent = color ?? AppColors.primary;

    final content = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 16, color: accent),
            const SizedBox(width: 6),
            Expanded(
              child: Text(title,
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: accent)),
            ),
          ],
        ),
        const SizedBox(height: 6),
        for (final line in lines)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 7, right: 8),
                  child: Container(
                    width: 4,
                    height: 4,
                    decoration: BoxDecoration(color: accent, shape: BoxShape.circle),
                  ),
                ),
                Expanded(
                  child: Text(line,
                      style: TextStyle(fontSize: 13.5, height: 1.55, color: style.foreground)),
                ),
              ],
            ),
          ),
      ],
    );

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: highlighted
          ? BlockCard(
              style: style,
              outlined: true,
              radius: 16,
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
              child: content,
            )
          : content,
    );
  }
}

class _WeekdayHeader extends StatelessWidget {
  const _WeekdayHeader();

  @override
  Widget build(BuildContext context) {
    const labels = ['일', '월', '화', '수', '목', '금', '토'];
    return Row(
      children: labels
          .map((l) => Expanded(
                child: Center(
                  child: Text(l,
                      style: TextStyle(
                          color: AppBlocks.cream.mutedOr,
                          fontWeight: FontWeight.w700,
                          fontSize: 12)),
                ),
              ))
          .toList(),
    );
  }
}
