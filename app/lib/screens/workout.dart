import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../api.dart';
import '../main.dart';
import '../widgets/common.dart';
import 'summary.dart';

/// 운동 세션 진행 화면.
///
/// AI 없음 — 카메라는 자리 표시자, 렙 카운트는 타이머로 자동 증가하는 목(mock) 데이터.
/// 다만 목 타이머도 `GET /me/plan`이 내려준 **목표 횟수**에 도달하면 멈추고 휴식으로 넘어간다.
///
/// 상태 기계: loading → ready → exercising ⇄ resting → (마지막 세트) → 저장 → 요약
enum _Phase { loading, ready, exercising, resting }

class WorkoutScreen extends StatefulWidget {
  final Map<String, dynamic> exercise;
  const WorkoutScreen({super.key, required this.exercise});

  @override
  State<WorkoutScreen> createState() => _WorkoutScreenState();
}

class _WorkoutScreenState extends State<WorkoutScreen> {
  // 계획을 못 받았을 때의 폴백. 초급 맨몸 프리셋(2×10/90초)보다 한 세트 많고 휴식은 짧은
  // 무난한 중간값 — 어떤 운동이든 "일단 오늘 할 수 있는 양"으로 성립한다.
  static const _fallbackSets = 3;
  static const _fallbackReps = 10;
  static const _fallbackRest = 60;

  static const _levelLabel = {
    'beginner': '초급',
    'intermediate': '중급',
    'advanced': '상급',
  };

  final _random = Random();
  final DateTime _startedAt = DateTime.now();
  final List<Map<String, dynamic>> _completedSets = [];

  _Phase _phase = _Phase.loading;
  String? _planError; // null이 아니면 폴백 계획으로 돌고 있다는 뜻

  int _targetSets = _fallbackSets;
  int _targetReps = _fallbackReps;
  int _restSec = _fallbackRest;
  String? _planMessage;
  String? _planHead;

  /// 진행 중인 세트 번호(1-based). 0이면 아직 시작 전.
  int _setNo = 0;

  Timer? _repTimer;
  Timer? _restTimer;
  int _reps = 0;
  final List<int> _formScores = [];
  int _restRemaining = 0;
  int _restTotal = 0;

  bool _posting = false;

  @override
  void initState() {
    super.initState();
    _loadPlan();
  }

  @override
  void dispose() {
    _repTimer?.cancel();
    _restTimer?.cancel();
    super.dispose();
  }

  // ---- 계획 ----

  Future<void> _loadPlan() async {
    setState(() {
      _phase = _Phase.loading;
      _planError = null;
    });
    try {
      final plan = await Api.instance.getPlan(widget.exercise['id'].toString());
      if (!mounted) return;
      setState(() {
        _targetSets = _asInt(plan['sets'], _fallbackSets);
        _targetReps = _asInt(plan['reps'], _fallbackReps);
        _restSec = _asInt(plan['rest_sec'], _fallbackRest);
        _planMessage = plan['message'] as String?;
        _planHead = _headline(plan['level'] as String?);
        _phase = _Phase.ready;
      });
    } catch (e) {
      if (!mounted) return;
      // 계획을 못 받아도 운동 자체는 성립해야 한다 → 기본값으로 진행하되 사실을 알린다.
      setState(() {
        _targetSets = _fallbackSets;
        _targetReps = _fallbackReps;
        _restSec = _fallbackRest;
        _planMessage = null;
        _planHead = _headline(null);
        _planError = '$e';
        _phase = _Phase.ready;
      });
    }
  }

  static int _asInt(Object? v, int fallback) =>
      v is int ? v : (v is num ? v.round() : (int.tryParse('$v') ?? fallback));

  String _headline(String? level) {
    final lv = _levelLabel[level];
    final rest = switch (_restSec) {
      < 60 => '$_restSec초',
      _ when _restSec % 60 == 0 => '${_restSec ~/ 60}분',
      _ => '${_restSec ~/ 60}분 ${_restSec % 60}초',
    };
    return '${lv == null ? '' : '$lv · '}$_targetSets세트 × $_targetReps회 · 휴식 $rest';
  }

  // ---- 상태 전이 ----

  void _startSet() {
    setState(() {
      _phase = _Phase.exercising;
      _setNo += 1;
      _reps = 0;
      _formScores.clear();
    });
    _restTimer?.cancel();
    _repTimer?.cancel();
    // 목 데이터: 3초에 1회. 실제 카메라/YOLO가 붙으면 이 타이머만 걷어내면 된다.
    _repTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (!mounted) return;
      setState(() {
        _reps++;
        _formScores.add(60 + _random.nextInt(41)); // 60~100
      });
      HapticFeedback.lightImpact();
      if (_reps >= _targetReps) _completeSet();
    });
  }

  /// 세트 종료 시 자세 판정을 받아온다.
  ///
  /// 카메라가 아직 없어 자리표시자 프레임을 보내지만, 각도 계산과 기준 판정은
  /// 백엔드 pose_eval이 실제로 수행한다 — 여기서 받은 checks는 진짜 산출물이다.
  /// 이게 없으면 요약·캘린더의 문장 분석이 "관절 데이터가 없어 분석할 수 없다"만 반복한다.
  /// 실패해도 세션 기록은 진행한다 (checks 없이 저장되고, 분석이 그 사실을 정직하게 알린다).
  Future<List<dynamic>?> _fetchChecks() async {
    try {
      final res = await Api.instance.postPoseFrame(
        exerciseId: widget.exercise['id'].toString(),
        frameBytes: Api.placeholderFrame,
      );
      final ev = res['evaluation'];
      if (ev is Map && ev['checks'] is List) return ev['checks'] as List;
    } catch (_) {
      // 무시 — 자세 판정 실패가 운동 기록을 막으면 안 된다.
    }
    return null;
  }

  /// 현재 세트를 기록에 넣는다. 목표 도달(자동)과 "세트 완료"(수동) 둘 다 여기로 온다.
  Future<void> _completeSet() async {
    _repTimer?.cancel();
    if (_reps > 0) {
      final set = <String, dynamic>{'reps': _reps, 'form_score': _avgFormScore ?? 0};
      final checks = await _fetchChecks();
      if (checks != null && checks.isNotEmpty) set['checks'] = checks;
      _completedSets.add(set);
      HapticFeedback.mediumImpact();
    }
    if (_setNo >= _targetSets) {
      _endWorkout();
      return;
    }
    _startRest();
  }

  void _startRest() {
    setState(() {
      _phase = _Phase.resting;
      _restTotal = _restSec;
      _restRemaining = _restSec;
      _reps = 0;
      _formScores.clear();
    });
    if (_restSec <= 0) {
      _startSet();
      return;
    }
    _restTimer?.cancel();
    _restTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      if (_restRemaining <= 1) {
        _restTimer?.cancel();
        HapticFeedback.mediumImpact();
        _startSet();
      } else {
        setState(() => _restRemaining -= 1);
      }
    });
  }

  void _addRest(int seconds) {
    setState(() {
      _restRemaining += seconds;
      _restTotal = max(_restTotal, _restRemaining);
    });
  }

  Future<void> _endWorkout() async {
    _repTimer?.cancel();
    _restTimer?.cancel();
    // 진행 중이던 세트가 남아 있으면 버리지 않고 기록에 넣는다.
    if (_reps > 0) {
      final set = <String, dynamic>{'reps': _reps, 'form_score': _avgFormScore ?? 0};
      final checks = await _fetchChecks();
      if (checks != null && checks.isNotEmpty) set['checks'] = checks;
      _completedSets.add(set);
      _reps = 0;
      _formScores.clear();
    }
    if (_completedSets.isEmpty) {
      if (mounted) Navigator.of(context).pop();
      return;
    }
    setState(() => _posting = true);
    try {
      final session = await Api.instance.postSession(
        exerciseId: widget.exercise['id'].toString(),
        startedAt: _startedAt,
        // 세트마다 _fetchChecks()로 받은 관절 판정이 들어 있다.
        // 판정을 못 받은 세트는 checks 없이 저장되고, 분석이 그 사실을 정직하게 알린다.
        sets: _completedSets,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        fadeRoute(context, (_) => SummaryScreen(session: session, exercise: widget.exercise)),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('저장 실패: $e')));
        setState(() => _posting = false);
      }
    }
  }

  // ---- 파생값 ----

  int? get _avgFormScore {
    if (_formScores.isEmpty) return null;
    return (_formScores.reduce((a, b) => a + b) / _formScores.length).round();
  }

  String _scoreLabel(int score) {
    if (score >= 80) return '좋은 자세예요';
    if (score >= 60) return '자세를 조금 더 신경 써보세요';
    return '자세가 흐트러졌어요';
  }

  static String _clock(int seconds) {
    if (seconds < 60) return '$seconds';
    return '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';
  }

  // ---- 빌드 ----

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: buildAppTheme(dark: true),
      child: Scaffold(
        appBar: AppBar(
          title: Text(
            widget.exercise['name'] as String? ?? '운동',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        body: SafeArea(
          top: false,
          child: _phase == _Phase.loading
              ? const Center(child: CircularProgressIndicator(color: AppDark.primary))
              : Column(
                  children: [
                    _statusBanner(),
                    Expanded(child: _stage()),
                    if (_completedSets.isNotEmpty) _completedStrip(),
                    _actions(),
                  ],
                ),
        ),
      ),
    );
  }

  /// 화면 최상단 고정 띠 — "지금 무슨 상태인지"와 "몇 세트인지"를 항상 붙들고 있는 자리.
  ///
  /// 운동/휴식 구분은 4중으로 전달한다(WCAG 1.4.1 색 단독 전달 금지):
  /// 배경색(라임 솔리드 / 중립 다크) + 아이콘 + 텍스트 라벨 + 아래 무대의 레이아웃 자체.
  Widget _statusBanner() {
    final (BlockStyle style, IconData icon, String label) = switch (_phase) {
      _Phase.exercising => (AppBlocks.gochujang, Icons.bolt_rounded, '운동 중'),
      _Phase.resting => (AppBlocks.navy, Icons.self_improvement_rounded, '휴식 중'),
      _ => (AppBlocks.darkNeutral, Icons.flag_outlined, '시작 전'),
    };
    final setNoShown = _setNo == 0 ? 1 : _setNo;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      child: Semantics(
        liveRegion: true,
        label: '$label, $_targetSets세트 중 $setNoShown세트',
        excludeSemantics: true,
        child: BlockCard(
          style: style,
          radius: 18,
          outlined: _phase != _Phase.exercising,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              Icon(icon, color: style.foreground, size: 24),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: style.foreground,
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.2,
                  ),
                ),
              ),
              Text.rich(
                TextSpan(
                  children: [
                    TextSpan(
                      text: '$setNoShown',
                      style: TextStyle(
                        color: style.foreground,
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        fontFeatures: const [FontFeature.tabularFigures()],
                      ),
                    ),
                    TextSpan(
                      text: ' / $_targetSets세트',
                      style: TextStyle(
                        color: style.mutedOr,
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _stage() => switch (_phase) {
        _Phase.resting => _restStage(),
        _Phase.exercising => _cameraStage(),
        _ => _readyStage(),
      };

  // --- 준비 ---

  Widget _readyStage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_planError != null) ...[
            ErrorCard(
              dark: true,
              message: '오늘의 계획을 불러오지 못했어요. 기본값($_fallbackSets세트 × $_fallbackReps회, '
                  '휴식 $_fallbackRest초)으로 진행합니다.',
              onRetry: _loadPlan,
            ),
            const SizedBox(height: 12),
          ],
          BlockCard(
            style: AppBlocks.darkNeutral,
            outlined: true,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('오늘의 계획',
                    style: TextStyle(
                        color: AppDark.foregroundMuted,
                        fontSize: 13,
                        fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                Text(
                  _planHead ?? '',
                  style: const TextStyle(
                      color: AppDark.foreground, fontSize: 20, fontWeight: FontWeight.w800),
                ),
                if (_planMessage != null) ...[
                  const SizedBox(height: 10),
                  Text(_planMessage!,
                      style: const TextStyle(
                          color: AppDark.foregroundMuted, fontSize: 14, height: 1.45)),
                ],
              ],
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: StatPill(
                  style: AppBlocks.tintNavy,
                  outlined: true,
                  center: true,
                  value: '$_targetSets',
                  unit: '세트',
                  label: '목표 세트',
                  icon: Icons.layers_outlined,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: StatPill(
                  style: AppBlocks.tintNavy,
                  outlined: true,
                  center: true,
                  value: '$_targetReps',
                  unit: '회',
                  label: '세트당 횟수',
                  icon: Icons.repeat_rounded,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: StatPill(
                  style: AppBlocks.tintNavy,
                  outlined: true,
                  center: true,
                  value: _restSec >= 60 ? _clock(_restSec) : '$_restSec',
                  unit: _restSec >= 60 ? '' : '초',
                  label: '세트 간 휴식',
                  icon: Icons.timer_outlined,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // --- 운동 중 (카메라) ---

  Widget _cameraStage() {
    final avg = _avgFormScore;
    final scoreColor = avg != null ? formScoreColor(avg, dark: true) : AppDark.foregroundMuted;
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final progress = _targetReps == 0 ? 0.0 : (_reps / _targetReps).clamp(0.0, 1.0);

    return Container(
      margin: const EdgeInsets.fromLTRB(16, 4, 16, 8),
      decoration: BoxDecoration(
        // 카메라 뷰포트는 실제 영상이 들어올 미디어 면 → 테마색이 아닌 순검정 유지.
        color: Colors.black,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppDark.primary.withValues(alpha: 0.45)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(18),
        child: Stack(
          fit: StackFit.expand,
          children: [
            // 뷰파인더는 "지금 측정하고 있다"는 신호 → 운동 중일 때만 그린다.
            const CustomPaint(painter: _ViewfinderPainter(color: AppDark.primary)),
            Center(
              child: Icon(Icons.accessibility_new_rounded,
                  color: AppDark.foregroundMuted.withValues(alpha: 0.22), size: 110),
            ),
            Positioned(
              top: 12,
              left: 12,
              child: _badge(
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.fiber_manual_record, size: 10, color: AppDark.error),
                    SizedBox(width: 6),
                    Text('측정 중',
                        style: TextStyle(
                            color: AppDark.foreground,
                            fontWeight: FontWeight.w700,
                            fontSize: 12)),
                  ],
                ),
              ),
            ),
            Positioned(
              top: 12,
              right: 12,
              child: _badge(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    FormScoreRing(
                      score: avg,
                      color: scoreColor,
                      trackColor: AppDark.surfaceMuted,
                      size: 56,
                      strokeWidth: 6,
                    ),
                    const SizedBox(height: 6),
                    SizedBox(
                      width: 92,
                      // 색 + 아이콘 + 문장 3중 표기 (WCAG 1.4.1).
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (avg != null) Icon(formScoreIcon(avg), size: 14, color: scoreColor),
                          Text(
                            avg != null ? _scoreLabel(avg) : '측정 준비 중',
                            textAlign: TextAlign.center,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                                color: scoreColor, fontWeight: FontWeight.w700, fontSize: 12),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            // 진행도는 뷰포트 하단에 얹는다 — 영상 면을 잃지 않으면서 항상 보인다.
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: Container(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 14),
                color: Colors.black.withValues(alpha: 0.62),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.baseline,
                      textBaseline: TextBaseline.alphabetic,
                      children: [
                        TweenAnimationBuilder<double>(
                          key: ValueKey(_reps),
                          tween: Tween(begin: reduceMotion ? 1.0 : 1.15, end: 1.0),
                          duration: const Duration(milliseconds: 200),
                          curve: Curves.easeOut,
                          builder: (context, scale, child) =>
                              Transform.scale(scale: scale, child: child),
                          child: Text('$_reps',
                              style: const TextStyle(
                                  color: AppDark.primary,
                                  fontSize: 56,
                                  height: 1.0,
                                  fontWeight: FontWeight.w800,
                                  fontFeatures: [FontFeature.tabularFigures()])),
                        ),
                        const SizedBox(width: 8),
                        Text('/ $_targetReps회',
                            style: const TextStyle(
                                color: AppDark.foreground,
                                fontSize: 20,
                                fontWeight: FontWeight.w700)),
                        const Spacer(),
                        Text('$_setNo세트 진행 중',
                            style: const TextStyle(
                                color: AppDark.foregroundMuted,
                                fontSize: 13,
                                fontWeight: FontWeight.w600)),
                      ],
                    ),
                    const SizedBox(height: 10),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(999),
                      child: LinearProgressIndicator(
                        value: progress,
                        minHeight: 8,
                        backgroundColor: AppDark.surfaceMuted,
                        valueColor: const AlwaysStoppedAnimation(AppDark.primary),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _badge({required Widget child}) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: Colors.black.withValues(alpha: 0.55),
          borderRadius: BorderRadius.circular(12),
        ),
        child: child,
      );

  // --- 휴식 중 ---

  /// 휴식 중에는 카메라 면을 아예 걷어낸다. 측정하지 않는 동안 검은 박스를 남겨두면
  /// 화면 절반이 죽고, "지금 쉬는 중"이라는 사실도 약해진다.
  Widget _restStage() {
    final fraction = _restTotal == 0 ? 0.0 : (_restRemaining / _restTotal).clamp(0.0, 1.0);
    const style = AppBlocks.navy;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
      child: BlockCard(
        style: style,
        radius: 18,
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
        child: LayoutBuilder(
          builder: (context, constraints) {
            // 세로 여유가 없으면 카운트다운 글자를 줄여 오버플로를 피한다.
            final big = constraints.maxHeight < 300 ? 72.0 : 104.0;
            return Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.self_improvement_rounded, color: style.foreground, size: 20),
                    const SizedBox(width: 8),
                    Text('다음 세트까지',
                        style: TextStyle(
                            color: style.mutedOr, fontSize: 15, fontWeight: FontWeight.w700)),
                  ],
                ),
                const SizedBox(height: 4),
                FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Semantics(
                    label: '남은 휴식 $_restRemaining초',
                    excludeSemantics: true,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.baseline,
                      textBaseline: TextBaseline.alphabetic,
                      children: [
                        Text(
                          _clock(_restRemaining),
                          style: TextStyle(
                            color: style.foreground,
                            fontSize: big,
                            height: 1.05,
                            fontWeight: FontWeight.w800,
                            fontFeatures: const [FontFeature.tabularFigures()],
                          ),
                        ),
                        const SizedBox(width: 6),
                        Text(_restRemaining < 60 ? '초' : '',
                            style: TextStyle(
                                color: style.mutedOr,
                                fontSize: 22,
                                fontWeight: FontWeight.w700)),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                ClipRRect(
                  borderRadius: BorderRadius.circular(999),
                  child: LinearProgressIndicator(
                    value: fraction,
                    minHeight: 8,
                    backgroundColor: AppDark.surfaceMuted,
                    valueColor: const AlwaysStoppedAnimation(AppDark.primary),
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  '다음은 ${_setNo + 1}세트 · 목표 $_targetReps회',
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      color: style.foreground, fontSize: 15, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: _restButton(
                        icon: Icons.add_rounded,
                        label: '30초 추가',
                        onPressed: _posting ? null : () => _addRest(30),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _restButton(
                        icon: Icons.skip_next_rounded,
                        label: '건너뛰기',
                        onPressed: _posting
                            ? null
                            : () {
                                _restTimer?.cancel();
                                _startSet();
                              },
                      ),
                    ),
                  ],
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _restButton({
    required IconData icon,
    required String label,
    required VoidCallback? onPressed,
  }) {
    return PressScale(
      child: OutlinedButton.icon(
        onPressed: onPressed,
        icon: Icon(icon, size: 18),
        label: Text(label, maxLines: 1, overflow: TextOverflow.ellipsis),
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(0, 48), // 최소 터치 타깃
          foregroundColor: AppBlocks.navy.foreground,
          side: BorderSide(color: AppBlocks.navy.foreground.withValues(alpha: 0.55)),
        ),
      ),
    );
  }

  // --- 완료한 세트 기록 ---

  Widget _completedStrip() {
    return SizedBox(
      height: 86,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: _completedSets.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, i) {
          final s = _completedSets[i];
          final score = _asInt(s['form_score'], 0);
          final color = formScoreColor(score, dark: true);
          return BlockCard(
            style: AppBlocks.tintNavy,
            outlined: true,
            radius: 14,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            semanticLabel: '${i + 1}세트 ${s['reps']}회, 폼 점수 $score점',
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${i + 1}세트',
                    style: const TextStyle(
                        color: AppDark.foregroundMuted,
                        fontSize: 12,
                        fontWeight: FontWeight.w700)),
                const SizedBox(height: 2),
                Text('${s['reps']}회',
                    style: const TextStyle(
                        color: AppDark.foreground, fontSize: 18, fontWeight: FontWeight.w800)),
                const SizedBox(height: 2),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(formScoreIcon(score), size: 12, color: color),
                    const SizedBox(width: 3),
                    Text('$score점',
                        style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w700)),
                  ],
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  // --- 하단 액션 ---

  Widget _actions() {
    final children = <Widget>[];

    if (_phase == _Phase.ready) {
      children.add(Expanded(
        child: PressScale(
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
              minimumSize: const Size(0, 52),
              backgroundColor: AppDark.primary,
              foregroundColor: AppDark.onPrimary,
            ),
            onPressed: _posting ? null : _startSet,
            icon: const Icon(Icons.play_arrow_rounded),
            label: const Text('1세트 시작'),
          ),
        ),
      ));
    } else {
      if (_phase == _Phase.exercising) {
        children.addAll([
          Expanded(
            child: PressScale(
              child: OutlinedButton(
                style: OutlinedButton.styleFrom(minimumSize: const Size(0, 52)),
                onPressed: _posting || _reps == 0 ? null : _completeSet,
                child: const Text('세트 완료', maxLines: 1, overflow: TextOverflow.ellipsis),
              ),
            ),
          ),
          const SizedBox(width: 12),
        ]);
      }
      children.add(Expanded(
        flex: _phase == _Phase.exercising ? 2 : 1,
        child: PressScale(
          child: FilledButton(
            // 원색 채움 전용 토큰. 그 위 전경은 화이트(6.38:1 AA).
            style: FilledButton.styleFrom(
              minimumSize: const Size(0, 52),
              backgroundColor: AppDark.dangerFill,
              foregroundColor: AppDark.foreground,
            ),
            onPressed: _posting ? null : _endWorkout,
            child: _posting
                ? const SizedBox(
                    height: 20,
                    width: 20,
                    child:
                        CircularProgressIndicator(strokeWidth: 2, color: AppDark.foreground))
                : const Text('운동 종료', maxLines: 1, overflow: TextOverflow.ellipsis),
          ),
        ),
      ));
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      child: Row(children: children),
    );
  }
}

/// 카메라 뷰파인더 느낌의 코너 브래킷 — HUD 톤의 시그니처 요소.
class _ViewfinderPainter extends CustomPainter {
  final Color color;
  const _ViewfinderPainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      // 검정 뷰포트 위 3:1(WCAG 1.4.11 그래픽 객체) 확보 — 0.55는 2.79:1로 미달이었다.
      ..color = color.withValues(alpha: 0.8)
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    const inset = 18.0;
    const armLength = 28.0;
    final corners = [
      const Offset(inset, inset),
      Offset(size.width - inset, inset),
      Offset(inset, size.height - inset),
      Offset(size.width - inset, size.height - inset),
    ];
    for (final c in corners) {
      final dx = c.dx < size.width / 2 ? 1.0 : -1.0;
      final dy = c.dy < size.height / 2 ? 1.0 : -1.0;
      canvas.drawLine(c, c + Offset(armLength * dx, 0), paint);
      canvas.drawLine(c, c + Offset(0, armLength * dy), paint);
    }
  }

  @override
  bool shouldRepaint(covariant _ViewfinderPainter oldDelegate) => oldDelegate.color != color;
}
