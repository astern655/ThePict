import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import '../api.dart';
import '../main.dart';
import '../widgets/common.dart';
import 'summary.dart';

/// 운동 세션 진행 화면.
///
/// 자세 측정 경로는 하나뿐이다: **세트마다 직접 촬영해 `/inference/video`에 올리는 것**.
/// 그때만 AI 엔진(YOLO)이 실제로 반복을 세고 회차별 자세를 판정하며, 그 결과가
/// 세트의 reps/form_score/checks가 된다. 갤러리에서 고르는 경로는 없다 — 바로 촬영해
/// 모델을 돌리고 지우는 흐름이다. 목(mock) 타이머로 렙을 세던 예전 경로도 없다.
///
/// 상태 기계: loading → ready → exercising(촬영 대기) → analyzing(분석 중)
///   → reviewing(저장/재촬영 결정) → [저장 시] resting ⇄ exercising → (마지막 세트) 저장 → 요약
///
/// 시안(The Fit iOS.dc.html, "운동 진행")을 그대로 따른다: 화면 자체는 **라이트**
/// (흰 글라스 카드·연한 틴트 타일·잉크 텍스트)이고, 촬영 대기(exercising)만 **다크 카메라
/// 오버레이**(코너 브래킷 + 하단 글라스 패널 + 평균 점수 링 + 단일 촬영 버튼)로 전체를 덮는다.
enum _Phase { loading, ready, exercising, analyzing, reviewing, resting }

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

  // 인라인 조절 한계. 되돌릴 수 없는 값이 아니므로 넉넉하되 실수 방지 선은 둔다.
  static const _minSets = 1, _maxSets = 12;
  static const _minReps = 1, _maxReps = 50;
  static const _minRest = 0, _maxRest = 300, _restStep = 15;

  static const _levelLabel = {
    'beginner': '초급',
    'intermediate': '중급',
    'advanced': '상급',
  };
  static const _levels = ['beginner', 'intermediate', 'advanced'];

  final DateTime _startedAt = DateTime.now();
  final List<Map<String, dynamic>> _completedSets = [];

  _Phase _phase = _Phase.loading;
  String? _planError; // null이 아니면 폴백 계획으로 돌고 있다는 뜻

  int _targetSets = _fallbackSets;
  int _targetReps = _fallbackReps;
  int _restSec = _fallbackRest;
  String? _planMessage;
  String? _level;

  /// 오늘의 계획 카드의 인라인 조절 패널(난이도·세트·횟수·휴식)이 펼쳐졌는지.
  bool _planOpen = false;

  /// 진행 중인 세트 번호(1-based). 0이면 아직 시작 전.
  int _setNo = 0;

  Timer? _restTimer;
  int _restRemaining = 0;
  int _restTotal = 0;

  bool _posting = false;

  /// 분석 대기 중인 세트(저장/재촬영 결정 전). null이면 review 단계가 아니다.
  Map<String, dynamic>? _pendingSet;
  Map<String, dynamic>? _pendingReport;

  @override
  void initState() {
    super.initState();
    _loadPlan();
  }

  @override
  void dispose() {
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
        _level = plan['level'] as String?;
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
        _level = null;
        _planError = '$e';
        _phase = _Phase.ready;
      });
    }
  }

  /// 난이도 세그먼트를 눌렀을 때. 서버의 난이도별 프리셋을 다시 받아 세트/횟수/휴식을 채운다
  /// (기존 [Api.getPlan]의 level 파라미터만 사용 — 새 API를 만들지 않는다). 프리셋을 못 받아도
  /// 난이도 선택 자체는 유지되고, 숫자는 아래 스테퍼로 직접 조절할 수 있다.
  Future<void> _selectLevel(String level) async {
    if (_level == level) return;
    setState(() => _level = level);
    HapticFeedback.selectionClick();
    try {
      final plan =
          await Api.instance.getPlan(widget.exercise['id'].toString(), level: level);
      if (!mounted) return;
      setState(() {
        _targetSets = _asInt(plan['sets'], _targetSets);
        _targetReps = _asInt(plan['reps'], _targetReps);
        _restSec = _asInt(plan['rest_sec'], _restSec);
      });
    } catch (_) {
      // 프리셋 로드 실패는 조용히 넘긴다 — 난이도 선택은 이미 반영됐고 숫자는 스테퍼로 조절 가능.
    }
  }

  void _bumpSets(int d) =>
      setState(() => _targetSets = (_targetSets + d).clamp(_minSets, _maxSets));
  void _bumpReps(int d) =>
      setState(() => _targetReps = (_targetReps + d).clamp(_minReps, _maxReps));
  void _bumpRest(int d) =>
      setState(() => _restSec = (_restSec + d).clamp(_minRest, _maxRest));

  /// 조절한 계획을 다음 세션에서도 기억하도록 베스트에포트로 저장한다(기존 [Api.putProgram]).
  /// 실패해도 이번 세션은 로컬 값(_targetSets 등)으로 이미 돌아가므로 조용히 넘어간다.
  void _persistPlan() {
    unawaited(
      Api.instance
          .putProgram(
            widget.exercise['id'].toString(),
            level: _level,
            sets: _targetSets,
            reps: _targetReps,
            restSec: _restSec,
          )
          .catchError((_) => <String, dynamic>{}),
    );
  }

  static int _asInt(Object? v, int fallback) =>
      v is int ? v : (v is num ? v.round() : (int.tryParse('$v') ?? fallback));

  String get _planHead {
    final lv = _level == null ? null : _levelLabel[_level];
    return '${lv == null ? '' : '$lv · '}$_targetSets세트 × $_targetReps회 · 휴식 ${_restText(_restSec)}';
  }

  /// 휴식 초를 사람이 읽는 라벨로: 45초 / 1분 / 1분 30초.
  static String _restText(int s) {
    if (s < 60) return '$s초';
    final m = s ~/ 60, r = s % 60;
    return r == 0 ? '$m분' : '$m분 $r초';
  }

  // ---- 상태 전이 ----

  /// 다음 세트의 촬영 대기 상태로 들어간다. 목 타이머는 없다 — 사용자가 직접
  /// 촬영할 때까지 기다린다.
  void _startSet() {
    _restTimer?.cancel();
    setState(() {
      _phase = _Phase.exercising;
      _setNo += 1;
      _pendingSet = null;
      _pendingReport = null;
    });
  }

  // ---- 영상으로 자세 측정 (유일한 실측 경로) ----

  /// 카메라로 직접 촬영한다. 갤러리 선택 경로는 없다 — 실패하면 폴백 없이 사유를 알린다.
  Future<void> _captureFromCamera() async {
    XFile? picked;
    try {
      picked = await ImagePicker().pickVideo(source: ImageSource.camera);
    } catch (e) {
      if (mounted) _toast('카메라를 열지 못했어요: $e');
      return;
    }
    if (picked != null) await _analyzeVideo(picked);
  }

  /// 촬영된 영상을 AI 엔진에 올리고, 결과를 저장/재촬영 결정 단계로 넘긴다.
  ///
  /// 반환된 `set`은 AI가 실제로 센 반복 횟수와 회차별 판정에서 나온 점수다.
  /// 여기서는 아직 세션에 기록하지 않는다 — 사용자가 [_saveSet]으로 확정해야 들어간다.
  Future<void> _analyzeVideo(XFile picked) async {
    setState(() => _phase = _Phase.analyzing);
    try {
      final bytes = await picked.readAsBytes();
      final res = await Api.instance.postWorkoutVideo(
        exerciseId: widget.exercise['id'].toString(),
        videoBytes: bytes,
        filename: picked.name,
      );
      if (!mounted) return;

      final set = Map<String, dynamic>.from(res['set'] as Map);
      final report = res['report'] as Map<String, dynamic>?;

      if (_asInt(set['reps'], 0) == 0) {
        // 반복을 하나도 못 셌다 — 기록하면 0회 세트가 남는다. 이유를 그대로 보여주고 재촬영시킨다.
        _toast(_reportProblem(report) ??
            '영상에서 반복 동작을 찾지 못했어요. 측면에서 전신이 나오게 다시 촬영해 주세요.');
        setState(() => _phase = _Phase.exercising);
        return;
      }

      setState(() {
        _pendingSet = set;
        _pendingReport = report;
        _phase = _Phase.reviewing;
      });
    } catch (e) {
      if (mounted) {
        _toast('$e');
        setState(() => _phase = _Phase.exercising);
      }
    }
  }

  /// 리포트의 영상 수준 경고(측면 아님, 검출률 낮음 등) 중 첫 문장.
  static String? _reportProblem(Map<String, dynamic>? report) {
    final issues = report?['video_issues'];
    if (issues is List && issues.isNotEmpty) {
      final first = issues.first;
      if (first is Map && first['message'] is String) return first['message'] as String;
    }
    return null;
  }

  void _toast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  /// 분석 대기 중인 세트를 확정해 기록에 넣는다. 마지막 세트면 바로 종료·저장한다.
  void _saveSet() {
    final set = _pendingSet;
    if (set == null) return;
    setState(() {
      _completedSets.add(set);
      _pendingSet = null;
      _pendingReport = null;
    });
    HapticFeedback.mediumImpact();
    if (_setNo >= _targetSets) {
      _endWorkout();
    } else {
      _startRest();
    }
  }

  /// 분석 결과를 버리고 같은 세트를 다시 촬영한다.
  void _retrySet() {
    setState(() {
      _pendingSet = null;
      _pendingReport = null;
      _phase = _Phase.exercising;
    });
  }

  void _startRest() {
    setState(() {
      _phase = _Phase.resting;
      _restTotal = _restSec;
      _restRemaining = _restSec;
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
    _restTimer?.cancel();
    if (_completedSets.isEmpty) {
      if (mounted) Navigator.of(context).pop();
      return;
    }
    setState(() => _posting = true);
    try {
      final session = await Api.instance.postSession(
        exerciseId: widget.exercise['id'].toString(),
        startedAt: _startedAt,
        // 모든 세트는 영상 분석으로 확정된 것뿐이다 — AI가 낸 form_score와 checks가 들어 있다.
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

  /// 지금까지 **실측된** 세트들의 평균 점수. 영상 분석 세트가 없으면 null.
  /// null은 "0점"이 아니라 "잰 적 없음"이다 — UI도 그렇게 표시해야 한다.
  int? get _avgFormScore {
    final scores = _completedSets.map((s) => s['form_score']).whereType<num>().toList();
    if (scores.isEmpty) return null;
    return (scores.reduce((a, b) => a + b) / scores.length).round();
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

  String get _exerciseName => widget.exercise['name'] as String? ?? '운동';

  // ---- 빌드 ----

  @override
  Widget build(BuildContext context) {
    // 시안대로 라이트 화면. 촬영 대기만 다크 카메라 오버레이가 전체를 덮는다.
    return Theme(
      data: buildAppTheme(dark: false),
      child: GradientBackground(
        child: Scaffold(
          backgroundColor: Colors.transparent,
          body: SafeArea(
            child: _phase == _Phase.loading
                ? const Center(child: CircularProgressIndicator())
                : Stack(
                    children: [
                      Column(
                        children: [
                          _header(),
                          _statusBanner(),
                          Expanded(child: _stage()),
                          if (_completedSets.isNotEmpty) _completedStrip(),
                          _actions(),
                        ],
                      ),
                      // 촬영 대기 = 시안의 pCapture. 헤더·배너·액션까지 통째로 덮는 다크 오버레이.
                      if (_phase == _Phase.exercising)
                        Positioned.fill(child: _captureOverlay()),
                    ],
                  ),
          ),
        ),
      ),
    );
  }

  /// 시안 상단: 원형 글라스 back 버튼 + 운동 이름. (Material AppBar 대신 시안 그대로의 커스텀 헤더.)
  Widget _header() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 16, 6),
      child: Row(
        children: [
          _roundBack(
            onTap: () => Navigator.of(context).maybePop(),
            bg: AppColors.surface,
            border: AppColors.border,
            iconColor: AppColors.foreground,
            shadow: true,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              _exerciseName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: AppColors.foreground,
                fontSize: 20,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// 원형 back 버튼 — 시안 36px 원. 터치 타깃은 48px로 넉넉히(시각 원은 40).
  Widget _roundBack({
    required VoidCallback onTap,
    required Color bg,
    Color? border,
    required Color iconColor,
    bool shadow = false,
  }) {
    return Semantics(
      button: true,
      label: '뒤로',
      child: PressScale(
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            customBorder: const CircleBorder(),
            child: SizedBox(
              width: 48,
              height: 48,
              child: Center(
                child: Container(
                  width: 40,
                  height: 40,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: bg,
                    shape: BoxShape.circle,
                    border: border == null ? null : Border.all(color: border),
                    boxShadow: shadow
                        ? const [BoxShadow(color: Color(0x141C2B2E), blurRadius: 3, offset: Offset(0, 1))]
                        : null,
                  ),
                  child: Icon(Icons.chevron_left_rounded, color: iconColor, size: 24),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// 시안 상태 배너 — bannerLabel + "N / M세트". 진행 중(분석/결과)은 코랄 채움, 그 외엔 연한 중립.
  ///
  /// 상태는 4중으로 전달한다(WCAG 1.4.1 색 단독 전달 금지):
  /// 배경색 + 아이콘 + 텍스트 라벨 + 아래 무대의 레이아웃 자체.
  Widget _statusBanner() {
    final (IconData icon, String label) = switch (_phase) {
      _Phase.exercising => (Icons.videocam_outlined, '촬영 대기'),
      _Phase.analyzing => (Icons.hourglass_top_rounded, '분석 중'),
      _Phase.reviewing => (Icons.fact_check_outlined, '결과 확인'),
      _Phase.resting => (Icons.self_improvement_rounded, '휴식 중'),
      _ => (Icons.flag_outlined, '시작 전'),
    };
    // 촬영/분석/결과는 코랄 채움(gochujang), 준비/휴식은 연한 중립(navy, 아웃라인으로 배경과 분리).
    final isActive = _phase == _Phase.exercising ||
        _phase == _Phase.analyzing ||
        _phase == _Phase.reviewing;
    final style = isActive ? AppBlocks.gochujang : AppBlocks.navy;
    final setNoShown = _setNo == 0 ? 1 : _setNo;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: Semantics(
        liveRegion: true,
        label: '$label, $_targetSets세트 중 $setNoShown세트',
        excludeSemantics: true,
        child: BlockCard(
          style: style,
          radius: 18,
          outlined: !isActive,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              Icon(icon, color: style.foreground, size: 22),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: style.foreground,
                    fontSize: 19,
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
                        fontSize: 24,
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
        _Phase.exercising => const SizedBox.expand(), // 다크 오버레이가 덮는다
        _Phase.analyzing => _analyzingStage(),
        _Phase.reviewing => _reviewStage(),
        _ => _readyStage(),
      };

  // --- 준비: 오늘의 계획 카드(+인라인 조절) + 스탯 타일 3연 ---

  Widget _readyStage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_planError != null) ...[
            ErrorCard(
              message: '오늘의 계획을 불러오지 못했어요. 기본값($_fallbackSets세트 × $_fallbackReps회, '
                  '휴식 $_fallbackRest초)으로 진행합니다.',
              onRetry: _loadPlan,
            ),
            const SizedBox(height: 12),
          ],
          _planCard(),
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
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _planCard() {
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // "오늘의 계획" 헤더 + "조절하기" 토글. 헤더 전체가 탭 영역.
          Semantics(
            button: true,
            label: _planOpen ? '오늘의 계획 조절 닫기' : '오늘의 계획 조절 열기',
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: () => setState(() => _planOpen = !_planOpen),
                borderRadius: BorderRadius.circular(12),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Expanded(
                            child: Text('오늘의 계획',
                                style: TextStyle(
                                    color: AppColors.foregroundMuted,
                                    fontSize: 13,
                                    fontWeight: FontWeight.w700)),
                          ),
                          const Text('조절하기',
                              style: TextStyle(
                                  color: AppColors.primaryText,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w700)),
                          const SizedBox(width: 4),
                          Transform.rotate(
                            angle: _planOpen ? pi : 0,
                            child: const Icon(Icons.keyboard_arrow_down_rounded,
                                color: AppColors.primaryText, size: 18),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(_planHead,
                          style: const TextStyle(
                              color: AppColors.foreground,
                              fontSize: 20,
                              fontWeight: FontWeight.w800)),
                      if (_planMessage != null) ...[
                        const SizedBox(height: 10),
                        Text(_planMessage!,
                            style: const TextStyle(
                                color: AppColors.foregroundMuted, fontSize: 14, height: 1.45)),
                      ],
                      const SizedBox(height: 10),
                      Text(
                        '세트마다 영상을 찍으면 AI가 반복 횟수와 자세를 실제로 판정해요. '
                        '$_exerciseName은 옆에서 찍어 주세요.',
                        style: const TextStyle(
                            color: AppColors.foregroundMuted, fontSize: 13, height: 1.45),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          if (_planOpen) _planEditor(),
        ],
      ),
    );
  }

  /// 인라인 조절 패널 — 난이도 세그먼트 + 세트/횟수/휴식 스테퍼.
  Widget _planEditor() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 14),
        const Divider(height: 1, thickness: 1, color: AppColors.border),
        const SizedBox(height: 14),
        const Text('난이도',
            style: TextStyle(
                color: AppColors.foregroundMuted, fontSize: 12, fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        _levelSegment(),
        const SizedBox(height: 16),
        _stepperRow('세트 수', '$_targetSets세트',
            onMinus: _targetSets > _minSets ? () => _bumpSets(-1) : null,
            onPlus: _targetSets < _maxSets ? () => _bumpSets(1) : null),
        const SizedBox(height: 12),
        _stepperRow('세트당 횟수', '$_targetReps회',
            onMinus: _targetReps > _minReps ? () => _bumpReps(-1) : null,
            onPlus: _targetReps < _maxReps ? () => _bumpReps(1) : null),
        const SizedBox(height: 12),
        _stepperRow('세트 간 휴식', _restText(_restSec),
            onMinus: _restSec > _minRest ? () => _bumpRest(-_restStep) : null,
            onPlus: _restSec < _maxRest ? () => _bumpRest(_restStep) : null),
      ],
    );
  }

  Widget _levelSegment() {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(11),
      ),
      padding: const EdgeInsets.all(3),
      child: Row(
        children: [
          for (final lv in _levels)
            Expanded(
              child: _segButton(
                label: _levelLabel[lv]!,
                selected: _level == lv,
                onTap: () => _selectLevel(lv),
              ),
            ),
        ],
      ),
    );
  }

  Widget _segButton({
    required String label,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(8),
          child: Container(
            height: 44,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: selected ? AppColors.surface : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
              boxShadow: selected
                  ? const [BoxShadow(color: Color(0x141C2B2E), blurRadius: 3, offset: Offset(0, 1))]
                  : null,
            ),
            child: Text(
              label,
              style: const TextStyle(
                  color: AppColors.foreground, fontSize: 14, fontWeight: FontWeight.w700),
            ),
          ),
        ),
      ),
    );
  }

  Widget _stepperRow(String label, String value,
      {required VoidCallback? onMinus, required VoidCallback? onPlus}) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Flexible(
          child: Text(label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  color: AppColors.foreground, fontSize: 15, fontWeight: FontWeight.w600)),
        ),
        Row(
          children: [
            _stepBtn(
              icon: Icons.remove_rounded,
              bg: AppColors.surfaceMuted,
              fg: AppColors.foreground,
              onTap: onMinus,
              semantic: '$label 줄이기',
            ),
            Semantics(
              label: '$label $value',
              excludeSemantics: true,
              child: Container(
                constraints: const BoxConstraints(minWidth: 60),
                alignment: Alignment.center,
                child: Text(value,
                    style: const TextStyle(
                        color: AppColors.foreground,
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        fontFeatures: [FontFeature.tabularFigures()])),
              ),
            ),
            _stepBtn(
              icon: Icons.add_rounded,
              bg: AppBlocks.tintGochujang.background,
              fg: AppColors.primaryText,
              onTap: onPlus,
              semantic: '$label 늘리기',
            ),
          ],
        ),
      ],
    );
  }

  /// 스테퍼 ±버튼 — 시안 34px 원. 터치 타깃 48px(시각 원 36).
  Widget _stepBtn({
    required IconData icon,
    required Color bg,
    required Color fg,
    required VoidCallback? onTap,
    required String semantic,
  }) {
    final enabled = onTap != null;
    return Semantics(
      button: true,
      enabled: enabled,
      label: semantic,
      child: PressScale(
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            customBorder: const CircleBorder(),
            child: SizedBox(
              width: 48,
              height: 48,
              child: Center(
                child: Opacity(
                  opacity: enabled ? 1 : 0.4,
                  child: Container(
                    width: 36,
                    height: 36,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(color: bg, shape: BoxShape.circle),
                    child: Icon(icon, size: 20, color: fg),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  // --- 분석 중 ---

  Widget _analyzingStage() {
    return const Padding(
      padding: EdgeInsets.fromLTRB(16, 6, 16, 8),
      child: GlassCard(
        radius: 22,
        padding: EdgeInsets.symmetric(horizontal: 20, vertical: 40),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              height: 44,
              width: 44,
              child: CircularProgressIndicator(strokeWidth: 3.5, color: AppColors.primary),
            ),
            SizedBox(height: 16),
            Text('AI가 영상을 분석하고 있어요',
                style: TextStyle(
                    color: AppColors.foreground, fontSize: 17, fontWeight: FontWeight.w800)),
            SizedBox(height: 8),
            Text('영상 길이에 따라 수 초~수십 초 걸릴 수 있어요.',
                textAlign: TextAlign.center,
                style:
                    TextStyle(color: AppColors.foregroundMuted, fontSize: 13, height: 1.4)),
          ],
        ),
      ),
    );
  }

  // --- 결과 확인(저장/재촬영 결정) — 좌 큰 렙 수 + 우상단 점수 링 + AI 피드백 ---

  Widget _reviewStage() {
    final set = _pendingSet;
    if (set == null) return const SizedBox.shrink();
    final reps = _asInt(set['reps'], 0);
    final rawScore = set['form_score'];
    final score = rawScore is num ? rawScore.round() : null;
    final color = score != null ? formScoreColor(score) : AppColors.foregroundMuted;
    final summary =
        (_pendingReport?['summary'] as List?)?.cast<String>() ?? const <String>[];
    final videoIssueMsg = _reportProblem(_pendingReport);

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          GlassCard(
            radius: 22,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text('$reps회',
                        style: const TextStyle(
                            color: AppColors.foreground,
                            fontSize: 34,
                            fontWeight: FontWeight.w800,
                            fontFeatures: [FontFeature.tabularFigures()])),
                    const Spacer(),
                    FormScoreRing(
                      score: score,
                      color: color,
                      trackColor: AppColors.surfaceMuted,
                      size: 60,
                      strokeWidth: 6,
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(score != null ? formScoreIcon(score) : Icons.remove_rounded,
                        size: 14, color: color),
                    const SizedBox(width: 4),
                    Text(score != null ? '$score점 · ${_scoreLabel(score)}' : '자세 점수 없음',
                        style:
                            TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w700)),
                  ],
                ),
                if (videoIssueMsg != null) ...[
                  const SizedBox(height: 12),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.error_outline, color: AppColors.error, size: 18),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(videoIssueMsg,
                            style: const TextStyle(
                                color: AppColors.error, fontSize: 13, height: 1.4)),
                      ),
                    ],
                  ),
                ],
                if (summary.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  const Divider(height: 1, thickness: 1, color: AppColors.border),
                  const SizedBox(height: 14),
                  const Text('AI 피드백',
                      style: TextStyle(
                          color: AppColors.foregroundMuted,
                          fontSize: 13,
                          fontWeight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  Text(summary.join('\n'),
                      style: const TextStyle(
                          color: AppColors.foreground, fontSize: 14, height: 1.55)),
                ],
              ],
            ),
          ),
          const SizedBox(height: 10),
          const Text('이 결과를 저장할지, 다시 촬영할지 골라주세요.',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.foregroundMuted, fontSize: 13)),
        ],
      ),
    );
  }

  // --- 휴식 중 — 중앙 큰 카운트다운 + 진행바 ---

  Widget _restStage() {
    final fraction =
        _restTotal == 0 ? 0.0 : (_restRemaining / _restTotal).clamp(0.0, 1.0);
    const style = AppBlocks.navy;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 8),
      child: BlockCard(
        style: style,
        radius: 22,
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 24),
        child: LayoutBuilder(
          builder: (context, constraints) {
            // 세로 여유가 없으면 카운트다운 글자를 줄여 오버플로를 피한다(시안 88px).
            final big = constraints.maxHeight < 300 ? 64.0 : 88.0;
            return Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.schedule_rounded, color: style.mutedOr, size: 18),
                    const SizedBox(width: 8),
                    Text('다음 세트까지',
                        style: TextStyle(
                            color: style.mutedOr, fontSize: 15, fontWeight: FontWeight.w700)),
                  ],
                ),
                const SizedBox(height: 6),
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
                    backgroundColor: AppColors.surface,
                    valueColor: const AlwaysStoppedAnimation(AppColors.primary),
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
          foregroundColor: AppColors.foreground,
          side: BorderSide(color: AppColors.foreground.withValues(alpha: 0.4)),
        ),
      ),
    );
  }

  // --- 완료한 세트 기록 스트립 ---

  Widget _completedStrip() {
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: SizedBox(
        height: 78,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          itemCount: _completedSets.length,
          separatorBuilder: (_, __) => const SizedBox(width: 8),
          itemBuilder: (context, i) {
            final s = _completedSets[i];
            // 영상으로 잰 세트만 점수가 있다. 없으면 0점이 아니라 '측정 안 함'이다.
            final rawScore = s['form_score'];
            final score = rawScore is num ? rawScore.round() : null;
            final color = score != null ? formScoreColor(score) : AppColors.foregroundMuted;
            return BlockCard(
              style: AppBlocks.tintNavy,
              outlined: true,
              radius: 14,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              semanticLabel: score != null
                  ? '${i + 1}세트 ${s['reps']}회, 폼 점수 $score점'
                  : '${i + 1}세트 ${s['reps']}회, 자세 측정 안 함',
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${i + 1}세트',
                      style: TextStyle(
                          color: AppBlocks.tintNavy.mutedOr,
                          fontSize: 12,
                          fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text('${s['reps']}회',
                      style: const TextStyle(
                          color: AppColors.foreground,
                          fontSize: 17,
                          fontWeight: FontWeight.w800)),
                  const SizedBox(height: 2),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(score != null ? Icons.check_rounded : Icons.remove_rounded,
                          size: 13, color: color),
                      const SizedBox(width: 3),
                      Text(score != null ? '$score점' : '측정 안 함',
                          style: TextStyle(
                              color: color, fontSize: 12, fontWeight: FontWeight.w700)),
                    ],
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  // --- 하단 액션 (라이트) ---

  Widget _actions() {
    final children = <Widget>[];

    switch (_phase) {
      case _Phase.ready:
        children.add(Expanded(
          child: PressScale(
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                minimumSize: const Size(0, 52),
                backgroundColor: AppColors.primary,
                foregroundColor: AppColors.onPrimary,
              ),
              onPressed: () {
                _persistPlan();
                _startSet();
              },
              icon: const Icon(Icons.play_arrow_rounded),
              label: const Text('1세트 시작', maxLines: 1, overflow: TextOverflow.ellipsis),
            ),
          ),
        ));
        break;

      case _Phase.reviewing:
        children.addAll([
          Expanded(
            child: PressScale(
              child: OutlinedButton.icon(
                style: OutlinedButton.styleFrom(minimumSize: const Size(0, 52)),
                onPressed: _retrySet,
                icon: const Icon(Icons.refresh_rounded, size: 18),
                label: const Text('다시 촬영', maxLines: 1, overflow: TextOverflow.ellipsis),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: PressScale(
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                  minimumSize: const Size(0, 52),
                  backgroundColor: AppColors.primary,
                  foregroundColor: AppColors.onPrimary,
                ),
                onPressed: _saveSet,
                icon: const Icon(Icons.check_rounded, size: 18),
                label: const Text('이 세트 저장', maxLines: 1, overflow: TextOverflow.ellipsis),
              ),
            ),
          ),
        ]);
        break;

      case _Phase.analyzing:
      case _Phase.resting:
        // 저장된 세트가 있으면 언제든 종료 가능. 분석 중엔 결과를 기다려야 하므로 비활성.
        if (_completedSets.isNotEmpty) {
          children.add(Expanded(
            child: PressScale(
              child: FilledButton(
                style: FilledButton.styleFrom(
                  minimumSize: const Size(0, 52),
                  backgroundColor: AppColors.error,
                  foregroundColor: const Color(0xFFFFFFFF),
                ),
                onPressed:
                    _posting || _phase == _Phase.analyzing ? null : _endWorkout,
                child: _posting
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Color(0xFFFFFFFF)))
                    : const Text('운동 종료', maxLines: 1, overflow: TextOverflow.ellipsis),
              ),
            ),
          ));
        } else {
          children.add(const Expanded(child: SizedBox.shrink()));
        }
        break;

      case _Phase.exercising:
      case _Phase.loading:
        // 촬영 대기는 다크 오버레이가 자체 버튼을 가진다 — 아래 액션 바는 비운다.
        return const SizedBox(height: 0);
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      child: Row(children: children),
    );
  }

  // --- 촬영 대기: 다크 카메라 오버레이 (시안 pCapture) ---

  /// 전체를 덮는 다크 카메라 오버레이. 코너 브래킷(코랄) + 상단 back·상태 필 + 하단 글라스
  /// 패널(평균 점수 링 + 안내 + [운동 종료?] + 단일 "촬영하기"). **갤러리 버튼 없음.**
  Widget _captureOverlay() {
    final setNoShown = _setNo == 0 ? 1 : _setNo;
    return DecoratedBox(
      // 카메라 뷰포트는 실제 영상이 들어올 미디어 면 → 테마색이 아닌 다크 스크림을 유지한다.
      decoration: const BoxDecoration(
        gradient: RadialGradient(
          center: Alignment(0, -0.3),
          radius: 1.1,
          colors: [Color(0xFF17191A), Color(0xFF000000)],
          stops: [0.0, 0.72],
        ),
      ),
      child: Column(
        children: [
          // 상단: back + "촬영 대기 · N/M세트"
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 6, 16, 0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                _roundBack(
                  onTap: () => Navigator.of(context).maybePop(),
                  bg: Colors.white.withValues(alpha: 0.14),
                  border: Colors.white.withValues(alpha: 0.25),
                  iconColor: Colors.white,
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.14),
                    borderRadius: BorderRadius.circular(19),
                    border: Border.all(color: Colors.white.withValues(alpha: 0.25)),
                  ),
                  child: Text(
                    '촬영 대기 · $setNoShown / $_targetSets세트',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      fontFeatures: [FontFeature.tabularFigures()],
                    ),
                  ),
                ),
              ],
            ),
          ),
          // 카메라 영역: 코너 브래킷(코랄)
          Expanded(
            child: CustomPaint(
              size: Size.infinite,
              painter: const _CornerBrackets(color: AppColors.primary),
            ),
          ),
          // 하단 글라스 패널
          _capturePanel(),
        ],
      ),
    );
  }

  Widget _capturePanel() {
    final avg = _avgFormScore;
    final ringColor = avg != null ? formScoreColor(avg, dark: true) : Colors.white;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.1),
        border: Border(top: BorderSide(color: Colors.white.withValues(alpha: 0.18))),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 평균 점수 링 + 라벨 (색 + 아이콘 + 문장 3중, WCAG 1.4.1)
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              FormScoreRing(
                score: avg,
                color: ringColor,
                trackColor: Colors.white.withValues(alpha: 0.25),
                size: 52,
                strokeWidth: 6,
              ),
              const SizedBox(height: 6),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (avg != null) ...[
                    Icon(formScoreIcon(avg), size: 13, color: ringColor),
                    const SizedBox(width: 4),
                  ],
                  Text(
                    avg != null ? '평균 $avg점' : '자세 측정 없음',
                    style: TextStyle(
                        color: ringColor, fontSize: 12, fontWeight: FontWeight.w700),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            '$_setNo세트를 촬영해 주세요 · 목표 $_targetReps회',
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                color: Colors.white, fontSize: 16, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 4),
          Text(
            '측면에서 전신이 나오게 찍으면 정확도가 올라가요.',
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
                color: Colors.white.withValues(alpha: 0.65), fontSize: 12.5, height: 1.4),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              if (_completedSets.isNotEmpty) ...[
                Expanded(
                  flex: 10,
                  child: PressScale(
                    child: OutlinedButton(
                      onPressed: _endWorkout,
                      style: OutlinedButton.styleFrom(
                        minimumSize: const Size(0, 50),
                        foregroundColor: AppDark.error, // 다크 위 밝은 레드(7.59:1)
                        backgroundColor: Colors.white.withValues(alpha: 0.12),
                        side: BorderSide(color: Colors.white.withValues(alpha: 0.3)),
                      ),
                      child: const Text('운동 종료',
                          maxLines: 1, overflow: TextOverflow.ellipsis),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
              ],
              Expanded(
                flex: 14,
                child: PressScale(
                  child: FilledButton.icon(
                    onPressed: _captureFromCamera,
                    style: FilledButton.styleFrom(
                      minimumSize: const Size(0, 50),
                      backgroundColor: AppColors.primary,
                      foregroundColor: AppColors.onPrimary, // 코랄 위 잉크(5.95:1 AA)
                    ),
                    icon: const Icon(Icons.videocam_rounded, size: 20),
                    label: const Text('촬영하기', maxLines: 1, overflow: TextOverflow.ellipsis),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// 카메라 영역 네 모서리의 L자 코너 브래킷 — 시안의 촬영 프레이밍 가이드.
/// 다크 스크림 위 3:1(WCAG 1.4.11 그래픽 객체) 확보를 위해 코랄을 알파 0.85로 그린다.
class _CornerBrackets extends CustomPainter {
  final Color color;
  const _CornerBrackets({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color.withValues(alpha: 0.85)
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    const inset = 22.0;
    const arm = 30.0;
    final corners = [
      const Offset(inset, inset),
      Offset(size.width - inset, inset),
      Offset(inset, size.height - inset),
      Offset(size.width - inset, size.height - inset),
    ];
    for (final c in corners) {
      final dx = c.dx < size.width / 2 ? 1.0 : -1.0;
      final dy = c.dy < size.height / 2 ? 1.0 : -1.0;
      canvas.drawLine(c, c + Offset(arm * dx, 0), paint);
      canvas.drawLine(c, c + Offset(0, arm * dy), paint);
    }
  }

  @override
  bool shouldRepaint(covariant _CornerBrackets oldDelegate) => oldDelegate.color != color;
}
