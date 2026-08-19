import 'package:flutter/material.dart';
import '../api.dart';
import '../main.dart';
import '../widgets/common.dart';
import 'root.dart';

/// iOS 인셋 그룹 셀 사이 헤어라인 — 시안 marginLeft:16.
const _cellDivider = Divider(height: 1, thickness: 1, indent: 16, color: AppColors.border);

/// iOS 인셋 그룹 섹션 헤더 — 카드 위 작은 회색 라벨(시안 13px w600 muted).
class _GroupHeader extends StatelessWidget {
  final String text;
  const _GroupHeader(this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 0, 4, 8),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.2,
          color: AppColors.foregroundMuted, // scaffold 위 4.54:1 AA
        ),
      ),
    );
  }
}

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  String _gender = 'male';
  final _ageCtrl = TextEditingController();
  final _heightCtrl = TextEditingController();
  final _weightCtrl = TextEditingController();
  final _goalCtrl = TextEditingController();
  bool _loading = false;
  String? _error;

  Future<void> _submit() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await Api.instance.updateProfile({
        'gender': _gender,
        'age': int.tryParse(_ageCtrl.text),
        'height_cm': double.tryParse(_heightCtrl.text),
        'weight_kg': double.tryParse(_weightCtrl.text),
        'goal': _goalCtrl.text.trim().isEmpty ? null : _goalCtrl.text.trim(),
      });
      if (!mounted) return;
      Navigator.of(context)
          .pushReplacement(fadeRoute(context, (_) => const RootScreen()));
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    // 시안 온보딩: 라지 타이틀 + 인셋 그룹(성별 세그먼트 + 값 입력 행) + 목표 카드 + 코랄 CTA.
    return GradientBackground(
      child: Scaffold(
        backgroundColor: Colors.transparent,
        body: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 40),
            children: [
              // iOS 라지 타이틀 + 서브텍스트.
              const Text(
                '내 정보',
                style: TextStyle(
                  fontSize: 34,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.5,
                  color: AppColors.foreground,
                ),
              ),
              const SizedBox(height: 6),
              const Text('맞춤 운동 강도를 계산하는 데 사용돼요.',
                  style:
                      TextStyle(color: AppColors.foregroundMuted, fontSize: 14, height: 1.35)),
              const SizedBox(height: 26),
              const _GroupHeader('기본 정보'),
              GlassCard(
                radius: 16,
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Column(
                  children: [
                    // 성별 — 시안 세그먼트 컨트롤(드롭다운 대신). 접근성 위해 각 세그먼트 최소 44 높이.
                    _Cell(
                      child: Row(
                        children: [
                          const Expanded(child: Text('성별', style: TextStyle(fontSize: 16))),
                          _GenderSegmented(
                            value: _gender,
                            onChanged: (v) => setState(() => _gender = v),
                          ),
                        ],
                      ),
                    ),
                    _cellDivider,
                    _ValueRow(label: '나이', controller: _ageCtrl, action: TextInputAction.next),
                    _cellDivider,
                    _ValueRow(label: '키 (cm)', controller: _heightCtrl, action: TextInputAction.next),
                    _cellDivider,
                    _ValueRow(label: '몸무게 (kg)', controller: _weightCtrl, action: TextInputAction.next),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              const _GroupHeader('목표'),
              GlassCard(
                radius: 16,
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: _Cell(
                  child: TextField(
                    controller: _goalCtrl,
                    textInputAction: TextInputAction.done,
                    style: const TextStyle(fontSize: 16, color: AppColors.foreground),
                    decoration: const InputDecoration(
                      hintText: '목표 (예: 근력 향상)',
                      hintStyle: TextStyle(color: AppColors.foregroundMuted, fontSize: 16),
                      isDense: true,
                      filled: false,
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: UnderlineInputBorder(
                        borderSide: BorderSide(color: AppColors.primary, width: 2),
                      ),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 16),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.error_outline, color: AppColors.error, size: 18),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(_error!, style: const TextStyle(color: AppColors.error)),
                    ),
                  ],
                ),
              ],
              const SizedBox(height: 28),
              // 솔리드 코랄 채움 CTA(GradientButton은 PressScale·포커스 링 내장).
              GradientButton(
                onPressed: _loading ? null : _submit,
                child: _loading
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: AppColors.foreground))
                    : const Text('시작하기'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 인셋 그룹의 한 행 — 시안 셀 패딩(14 16).
class _Cell extends StatelessWidget {
  final Widget child;
  const _Cell({required this.child});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: child,
    );
  }
}

/// 라벨(좌) + 우측 정렬 숫자 입력 행. 시안 나이/키/몸무게 셀.
class _ValueRow extends StatelessWidget {
  final String label;
  final TextEditingController controller;
  final TextInputAction action;
  const _ValueRow({required this.label, required this.controller, required this.action});

  @override
  Widget build(BuildContext context) {
    return _Cell(
      child: Row(
        children: [
          Expanded(child: Text(label, style: const TextStyle(fontSize: 16))),
          SizedBox(
            width: 120,
            child: TextField(
              controller: controller,
              keyboardType: TextInputType.number,
              textInputAction: action,
              textAlign: TextAlign.end,
              style: const TextStyle(fontSize: 16, color: AppColors.foreground),
              decoration: const InputDecoration(
                isDense: true,
                filled: false,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: UnderlineInputBorder(
                  borderSide: BorderSide(color: AppColors.primary, width: 2),
                ),
                contentPadding: EdgeInsets.zero,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 성별 세그먼트 컨트롤 — 시안: 트랙 surfaceMuted, 선택 셀 흰 배경 + 미세 그림자.
/// 각 세그먼트는 라디오처럼 동작(Semantics selected). 접근성 최소 터치 44 높이 확보.
class _GenderSegmented extends StatelessWidget {
  final String value;
  final ValueChanged<String> onChanged;
  const _GenderSegmented({required this.value, required this.onChanged});

  static const _options = [
    ('male', '남성'),
    ('female', '여성'),
    ('other', '기타'),
  ];

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted, // 시안 세그먼트 트랙 #E7EEEC
        borderRadius: BorderRadius.circular(9),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final o in _options)
            _segment(o.$1, o.$2, o.$1 == value),
        ],
      ),
    );
  }

  Widget _segment(String key, String label, bool selected) {
    return Semantics(
      button: true,
      selected: selected,
      label: selected ? '$label, 선택됨' : label,
      excludeSemantics: true,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => onChanged(key),
          borderRadius: BorderRadius.circular(7),
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: selected ? AppColors.surface : Colors.transparent,
                borderRadius: BorderRadius.circular(7),
                boxShadow: selected
                    ? const [
                        BoxShadow(
                          color: Color(0x141C2B2E),
                          blurRadius: 3,
                          offset: Offset(0, 1),
                        ),
                      ]
                    : null,
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 14),
                child: Center(
                  widthFactor: 1,
                  child: Text(
                    label,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: AppColors.foreground, // 흰/트랙 위 13:1↑
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
