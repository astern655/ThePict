import 'package:flutter/material.dart';
import '../api.dart';
import '../main.dart';
import 'root.dart';

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
    return Scaffold(
      appBar: AppBar(title: const Text('내 정보 입력')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: ListView(
          children: [
            Text('기본 정보를 입력해주세요', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            const Text('맞춤 운동 강도를 계산하는 데 사용돼요.',
                style: TextStyle(color: AppColors.foregroundMuted, fontSize: 13)),
            const SizedBox(height: 20),
            DropdownButtonFormField<String>(
              initialValue: _gender,
              decoration: const InputDecoration(labelText: '성별', border: OutlineInputBorder()),
              items: const [
                DropdownMenuItem(value: 'male', child: Text('남성')),
                DropdownMenuItem(value: 'female', child: Text('여성')),
                DropdownMenuItem(value: 'other', child: Text('기타')),
              ],
              onChanged: (v) => setState(() => _gender = v ?? 'male'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _ageCtrl,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: '나이', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _heightCtrl,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: '키 (cm)', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _weightCtrl,
              keyboardType: TextInputType.number,
              decoration:
                  const InputDecoration(labelText: '몸무게 (kg)', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _goalCtrl,
              decoration: const InputDecoration(labelText: '목표', border: OutlineInputBorder()),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: AppColors.error)),
            ],
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _loading ? null : _submit,
              child: _loading
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.onPrimary))
                  : const Text('시작하기'),
            ),
          ],
        ),
      ),
    );
  }
}
