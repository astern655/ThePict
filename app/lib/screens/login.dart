import 'package:flutter/material.dart';
import '../api.dart';
import '../main.dart';
import 'onboarding.dart';
import 'root.dart';

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
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // 브랜드 로고 자리 — 아이콘 + 워드마크
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: AppColors.primary,
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: const Icon(Icons.fitness_center, color: AppColors.onPrimary, size: 28),
                  ),
                  const SizedBox(width: 12),
                  Text('HOHOWATT',
                      style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                            fontSize: 26,
                            letterSpacing: 1,
                          )),
                ],
              ),
              const SizedBox(height: 8),
              const Text('AI가 자세를 봐주는 셀프 트레이닝',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: AppColors.foregroundMuted, fontSize: 14)),
              const SizedBox(height: 48),
              Text(_isRegister ? '회원가입' : '로그인',
                  style: Theme.of(context).textTheme.titleLarge, textAlign: TextAlign.center),
              const SizedBox(height: 24),
              TextField(
                controller: _emailCtrl,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(
                  labelText: '이메일',
                  prefixIcon: Icon(Icons.mail_outline),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _passwordCtrl,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: '비밀번호',
                  prefixIcon: Icon(Icons.lock_outline),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Row(
                  children: [
                    const Icon(Icons.error_outline, color: AppColors.error, size: 18),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(_error!, style: const TextStyle(color: AppColors.error)),
                    ),
                  ],
                ),
              ],
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _loading ? null : _submit,
                child: _loading
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: AppColors.onPrimary))
                    : Text(_isRegister ? '가입하기' : '로그인'),
              ),
              const SizedBox(height: 4),
              TextButton(
                onPressed: _loading ? null : () => setState(() => _isRegister = !_isRegister),
                child: Text(_isRegister ? '이미 계정이 있나요? 로그인' : '계정이 없나요? 회원가입'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
