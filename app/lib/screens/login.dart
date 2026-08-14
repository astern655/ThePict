import 'package:flutter/material.dart';
import '../api.dart';
import '../main.dart';
import '../widgets/common.dart';
import 'onboarding.dart';
import 'root.dart';

/// iOS 인셋 그룹 셀용 데코레이션 — 흰 카드 안에서 필드 자체 배경/보더를 지우고,
/// 포커스 시에만 코랄 언더라인(흰 위 4.96:1, 1.4.11의 3:1 충족)으로 위치를 알린다.
InputDecoration _cellDecoration(String label, IconData icon) => InputDecoration(
      labelText: label,
      prefixIcon: Icon(icon),
      filled: false,
      border: InputBorder.none,
      enabledBorder: InputBorder.none,
      focusedBorder: const UnderlineInputBorder(
        borderSide: BorderSide(color: AppColors.primary, width: 2),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
    );

/// iOS 그룹 셀 사이 헤어라인 — 텍스트 시작점(아이콘 뒤)까지 들여쓴다.
const _cellDivider = Divider(height: 1, thickness: 1, indent: 52, color: AppColors.border);

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  bool _isRegister = false;
  bool _loading = false;
  String? _error;

  Future<void> _submit() async {
    final email = _emailCtrl.text.trim();
    final password = _passwordCtrl.text;
    if (email.isEmpty || password.isEmpty) {
      setState(() => _error = '이메일과 비밀번호를 입력하세요.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (_isRegister) {
        await Api.instance.register(email, password);
      } else {
        await Api.instance.login(email, password);
      }
      if (!mounted) return;
      Navigator.of(context).pushReplacement(fadeRoute(
        context,
        (_) => _isRegister ? const OnboardingScreen() : const RootScreen(),
      ));
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    // 크리스탈 글라스: scaffold를 밝은 산호↔청록 백드롭으로 감싸고, 브랜드 로크업과
    // 입력 그룹 두 개를 프로스티드 글라스 카드로 띄운다(포컬 표면만 — 프리미엄 로그인).
    return GradientBackground(
      child: Scaffold(
        backgroundColor: Colors.transparent,
        body: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
            child: ConstrainedBox(
              // 큰 화면에서 폼이 과하게 늘어나지 않게 상한만 준다(iOS 톤: 좁은 컬럼).
              constraints: const BoxConstraints(maxWidth: 460),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 40),
                  // 시안(29행): 상단 중앙 정적 로고 120×120 contain + 라지 타이틀. 브랜드 로크업 카드 없음.
                  // animate:false — 크로스페이드/회전 없이 정지 로고(사용자: 로그인에 애니메이션 금지).
                  const Center(child: AppLogo(size: 120, animate: false)),
                  const SizedBox(height: 34),
                  // iOS 라지 타이틀 — 좌측 정렬, 폼 섹션의 머리(시안 margin:34 0 18).
                  Text(
                    _isRegister ? '회원가입' : '로그인',
                    style: const TextStyle(
                      fontSize: 34,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.5,
                      color: AppColors.foreground,
                    ),
                  ),
                  const SizedBox(height: 18),
                  // iOS 인셋 그룹 — 이메일/비밀번호 셀을 흰 카드 안 헤어라인으로 묶는다(시안 radius 16).
                  GlassCard(
                    radius: 16,
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
                    child: Column(
                      children: [
                        TextField(
                          controller: _emailCtrl,
                          keyboardType: TextInputType.emailAddress,
                          textInputAction: TextInputAction.next,
                          decoration: _cellDecoration('이메일', Icons.mail_outline),
                        ),
                        _cellDivider,
                        TextField(
                          controller: _passwordCtrl,
                          obscureText: true,
                          textInputAction: TextInputAction.done,
                          onSubmitted: _loading ? null : (_) => _submit(),
                          decoration: _cellDecoration('비밀번호', Icons.lock_outline),
                        ),
                      ],
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 14),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(Icons.error_outline, color: AppColors.error, size: 18),
                        const SizedBox(width: 6),
                        Expanded(
                          child:
                              Text(_error!, style: const TextStyle(color: AppColors.error)),
                        ),
                      ],
                    ),
                  ],
                  const SizedBox(height: 24),
                  // 솔리드 코랄 채움 CTA(GradientButton은 PressScale·포커스 링 내장).
                  GradientButton(
                    onPressed: _loading ? null : _submit,
                    child: _loading
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: AppColors.foreground))
                        : Text(_isRegister ? '가입하기' : '로그인'),
                  ),
                  const SizedBox(height: 4),
                  TextButton(
                    onPressed:
                        _loading ? null : () => setState(() => _isRegister = !_isRegister),
                    child: Text(_isRegister ? '이미 계정이 있나요? 로그인' : '계정이 없나요? 회원가입'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
