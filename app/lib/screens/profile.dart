import 'package:flutter/material.dart';
import '../api.dart';
import '../main.dart';
import '../widgets/common.dart';
import 'login.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

/// `/sessions`에서 파생한 운동 통계. 프로필 폼과 **독립**으로 로드된다 —
/// 통계가 실패해도 폼은 계속 쓸 수 있어야 한다.
class _Stats {
  final int totalReps;
  final int activeDays;
  final double? avgForm;
  final int streak;

  const _Stats({
    required this.totalReps,
    required this.activeDays,
    required this.avgForm,
    required this.streak,
  });
}

String _compact(num v) {
  if (v < 1000) return '${v.round()}';
  if (v < 10000) return '${(v / 1000).toStringAsFixed(1)}k';
  return '${(v / 1000).round()}k';
}

/// 대한비만학회 기준 구간. 색만으로 구분하지 않으려고 라벨을 항상 함께 보여준다.
String _bmiLabel(double bmi) {
  if (bmi < 18.5) return '저체중';
  if (bmi < 23) return '정상';
  if (bmi < 25) return '과체중';
  return '비만';
}

class _ProfileScreenState extends State<ProfileScreen> {
  late Future<Map<String, dynamic>> _profileFuture;
  late Future<_Stats> _statsFuture;

  final _ageCtrl = TextEditingController();
  final _heightCtrl = TextEditingController();
  final _weightCtrl = TextEditingController();
  final _goalCtrl = TextEditingController();
  String _gender = 'male';
  String? _email;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _profileFuture = _loadProfile();
    _statsFuture = _loadStats();
  }

  Future<Map<String, dynamic>> _loadProfile() => Api.instance.getProfile().then((p) {
        _email = p['email'] as String?;
        _gender = p['gender'] as String? ?? 'male';
        _ageCtrl.text = p['age']?.toString() ?? '';
        _heightCtrl.text = p['height_cm']?.toString() ?? '';
        _weightCtrl.text = p['weight_kg']?.toString() ?? '';
        _goalCtrl.text = p['goal']?.toString() ?? '';
        return p;
      });

  @override
  void dispose() {
    _ageCtrl.dispose();
    _heightCtrl.dispose();
    _weightCtrl.dispose();
    _goalCtrl.dispose();
    super.dispose();
  }

  Future<_Stats> _loadStats() async {
    final sessions = (await Api.instance.getSessions()).cast<Map<String, dynamic>>();
    var totalReps = 0;
    var formSum = 0.0;
    var formCount = 0;
    final days = <DateTime>{};
    for (final s in sessions) {
      totalReps += (s['total_reps'] as num?)?.toInt() ?? 0;
      final f = s['avg_form_score'] as num?;
      if (f != null) {
        formSum += f.toDouble();
        formCount += 1;
      }
      final d = DateTime.tryParse(s['date'].toString());
      if (d != null) days.add(DateTime(d.year, d.month, d.day));
    }

    // 스트릭: 오늘(또는 어제)부터 하루씩 거슬러 올라가며 끊길 때까지.
    // 어제까지 허용하는 이유 — 오늘 아직 운동 전이라고 스트릭이 0으로 보이면 안 된다.
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    var cursor = days.contains(today) ? today : today.subtract(const Duration(days: 1));
    var streak = 0;
    while (days.contains(cursor)) {
      streak += 1;
      cursor = cursor.subtract(const Duration(days: 1));
    }

    return _Stats(
      totalReps: totalReps,
      activeDays: days.length,
      avgForm: formCount == 0 ? null : formSum / formCount,
      streak: streak,
    );
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await Api.instance.updateProfile({
        'gender': _gender,
        'age': int.tryParse(_ageCtrl.text),
        'height_cm': double.tryParse(_heightCtrl.text),
        'weight_kg': double.tryParse(_weightCtrl.text),
        'goal': _goalCtrl.text.trim().isEmpty ? null : _goalCtrl.text.trim(),
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('저장되었습니다')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('저장 실패: $e')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _logout() {
    Api.instance.logout();
    Navigator.of(context).pushAndRemoveUntil(
      fadeRoute(context, (_) => const LoginScreen()),
      (route) => false,
    );
  }

  Future<void> _deleteAccount() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('계정을 삭제할까요?'),
        content: const Text('삭제한 계정과 기록은 되돌릴 수 없습니다.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('취소')),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Semantics(
              hint: '되돌릴 수 없는 파괴적 작업입니다',
              child: const Text('삭제', style: TextStyle(color: AppColors.error)),
            ),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await Api.instance.deleteAccount();
      Api.instance.logout();
      if (mounted) {
        Navigator.of(context).pushAndRemoveUntil(
          fadeRoute(context, (_) => const LoginScreen()),
          (route) => false,
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('삭제 실패: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('프로필'),
        actions: [
          IconButton(tooltip: '로그아웃', icon: const Icon(Icons.logout), onPressed: _logout)
        ],
      ),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _profileFuture,
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
                  onRetry: () => setState(() => _profileFuture = _loadProfile()),
                ),
              ),
            );
          }
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
            children: [
              _hero(),
              const SizedBox(height: 12),
              _statsSection(),
              const SizedBox(height: 12),
              _programEntryCard(),
              const SizedBox(height: 12),
              _bmiCard(),
              const SizedBox(height: 12),
              _formCard(),
              const SizedBox(height: 14),
              PressScale(
                child: FilledButton(
                  onPressed: _saving ? null : _save,
                  child: _saving
                      ? const SizedBox(
                          height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('저장'),
                ),
              ),
              const SizedBox(height: 24),
              _dangerCard(),
            ],
          );
        },
      ),
    );
  }

  /// 히어로 — 고추장 솔리드. 화면 최상단을 가장 진한 면으로 눌러 위계를 만든다.
  Widget _hero() {
    const style = AppBlocks.gochujang;
    return BlockCard(
      style: style,
      padding: const EdgeInsets.all(20),
      child: Row(
        children: [
          Container(
            width: 52,
            height: 52,
            // raw hex 대신 토큰으로 — 값은 같지만 팔레트가 바뀔 때 같이 따라간다.
            // BlockStyle 필드 접근은 const 평가가 안 되므로 const를 뗀다.
            decoration: const BoxDecoration(
              color: AppColors.onPrimary,
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.person, color: AppColors.primary, size: 28),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('내 계정',
                    style:
                        TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: style.mutedOr)),
                const SizedBox(height: 4),
                Text(
                  _email ?? '이메일 없음',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, height: 1.25),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// 통계 3연 — 프로필 폼과 별도 Future. 실패해도 아래 폼은 살아있다.
  Widget _statsSection() {
    return FutureBuilder<_Stats>(
      future: _statsFuture,
      builder: (context, snap) {
        Widget body;
        if (snap.connectionState != ConnectionState.done) {
          body = const BlockCard(
            style: AppBlocks.cream,
            outlined: true,
            padding: EdgeInsets.symmetric(vertical: 28),
            child: Center(
              child: SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2)),
            ),
          );
        } else if (snap.hasError) {
          body = ErrorCard(
            message: '운동 통계를 불러오지 못했습니다. 프로필 수정은 그대로 가능합니다.',
            onRetry: () => setState(() => _statsFuture = _loadStats()),
          );
        } else {
          final s = snap.data!;
          body = Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: StatPill(
                      style: AppBlocks.navy,
                      value: _compact(s.totalReps),
                      unit: '렙',
                      label: '누적 렙 수',
                      icon: Icons.fitness_center_rounded,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: StatPill(
                      style: AppBlocks.crimson,
                      value: '${s.activeDays}',
                      unit: '일',
                      label: '총 운동일',
                      icon: Icons.event_available_rounded,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: StatPill(
                      style: AppBlocks.gochujang,
                      value: s.avgForm == null ? '–' : '${s.avgForm!.round()}',
                      unit: s.avgForm == null ? null : '점',
                      label: '평균 폼 점수',
                      icon: Icons.speed_rounded,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Align(
                alignment: Alignment.centerLeft,
                child: StreakBadge(days: s.streak, style: AppBlocks.tintCrimson),
              ),
            ],
          );
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 8),
              child: Text('운동 통계',
                  style: Theme.of(context).textTheme.titleMedium),
            ),
            body,
          ],
        );
      },
    );
  }

  /// 운동 프로그램 설정 입구.
  /// 프로필 화면은 이미 길다 — 난이도/세트/횟수/휴식 편집기는 운동 개수만큼 늘어나므로
  /// 여기 인라인으로 펼치지 않고 별도 화면([ProgramSettingsScreen])으로 뺐다.
  Widget _programEntryCard() {
    const style = AppBlocks.tintNavy;
    return BlockCard(
      style: style,
      outlined: true,
      padding: const EdgeInsets.all(18),
      semanticLabel: '운동 프로그램 설정. 난이도, 세트 수, 횟수, 휴식 시간을 운동별로 정합니다.',
      onTap: () => Navigator.of(context).push(
        fadeRoute(context, (_) => const ProgramSettingsScreen()),
      ),
      child: Row(
        children: [
          const Icon(Icons.tune_rounded, color: AppColors.primary),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('운동 프로그램 설정',
                    style: TextStyle(
                        fontSize: 15, fontWeight: FontWeight.w800, color: style.foreground)),
                const SizedBox(height: 4),
                Text('운동별로 난이도·세트 수·횟수·휴식 시간을 직접 정할 수 있어요.',
                    style: TextStyle(fontSize: 13, height: 1.4, color: style.mutedOr)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Icon(Icons.chevron_right_rounded, color: style.mutedOr),
        ],
      ),
    );
  }

  /// BMI — 서버에 없는 파생값. 입력 중인 키·몸무게로 즉시 계산된다.
  Widget _bmiCard() {
    final h = double.tryParse(_heightCtrl.text);
    final w = double.tryParse(_weightCtrl.text);
    final bmi = (h != null && h > 0 && w != null && w > 0) ? w / ((h / 100) * (h / 100)) : null;
    const style = AppBlocks.tintNavy;

    return BlockCard(
      style: style,
      outlined: true,
      padding: const EdgeInsets.all(18),
      semanticLabel: bmi == null
          ? 'BMI: 키와 몸무게를 입력하면 계산됩니다'
          : 'BMI ${bmi.toStringAsFixed(1)}, ${_bmiLabel(bmi)}',
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: bmi == null
                ? Text('키와 몸무게를 입력하면 BMI가 계산됩니다.',
                    style: TextStyle(fontSize: 13, color: style.mutedOr))
                : BigStat(
                    style: style,
                    value: bmi.toStringAsFixed(1),
                    caption: '체질량지수 (BMI)',
                    size: 40,
                  ),
          ),
          if (bmi != null)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
              decoration: BoxDecoration(
                color: AppBlocks.navy.background,
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(_bmiLabel(bmi),
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: AppBlocks.navy.foreground,
                  )),
            ),
        ],
      ),
    );
  }

  Widget _formCard() {
    return BlockCard(
      style: AppBlocks.cream,
      outlined: true, // 크림 scaffold 위 1.07:1 — 폼 카드 경계를 살린다
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('신체 정보', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 14),
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
            // BMI 카드를 실시간으로 갱신하기 위한 재빌드.
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(labelText: '키 (cm)', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _weightCtrl,
            keyboardType: TextInputType.number,
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(labelText: '몸무게 (kg)', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _goalCtrl,
            decoration: const InputDecoration(labelText: '목표', border: OutlineInputBorder()),
          ),
        ],
      ),
    );
  }

  Widget _dangerCard() {
    return BlockCard(
      style: AppBlocks.tintCrimson,
      outlined: true,
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('계정 삭제',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          Text('삭제한 계정과 운동 기록은 되돌릴 수 없습니다.',
              style: TextStyle(fontSize: 13, color: AppBlocks.tintCrimson.mutedOr)),
          const SizedBox(height: 14),
          OutlinedButton.icon(
            onPressed: _deleteAccount,
            style: OutlinedButton.styleFrom(
              foregroundColor: AppColors.error,
              side: const BorderSide(color: AppColors.error),
              minimumSize: const Size(0, 48),
            ),
            icon: const Icon(Icons.delete_outline),
            label: const Text('계정 삭제'),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 운동 프로그램 설정
//
// 백엔드(`program.py`)의 우선순위: 개인 설정 > 점진 증가 > 난이도 프리셋 (필드 단위).
// 화면도 이 순서를 그대로 보여준다 — 지금 적용 중인 값이 셋 중 어디서 왔는지를
// `/me/plan`의 `source`/`message`로 못 박고, 그 아래에서 덮어쓰게 한다.
//
// 프리셋 숫자는 **앱에 복제하지 않는다.** 여기에 베껴두면 백엔드 프리셋이 바뀔 때
// 조용히 어긋난다. 화면에 보이는 모든 수치는 `/me/plan` 응답에서 온 것이다.
// ---------------------------------------------------------------------------

const _levelLabels = <String, String>{
  'beginner': '초급',
  'intermediate': '중급',
  'advanced': '상급',
};

/// 저장 한계 — 백엔드 `ProgramOverride`의 Field(ge/le)와 같은 값.
/// 서버가 막더라도 앱에서 먼저 막는다(0세트·음수 휴식이 서버까지 가지 않게).
const _limits = <String, (int, int)>{
  'sets': (1, 10),
  'reps': (1, 100),
  'rest_sec': (0, 600),
};

class ProgramSettingsScreen extends StatefulWidget {
  const ProgramSettingsScreen({super.key});

  @override
  State<ProgramSettingsScreen> createState() => _ProgramSettingsScreenState();
}

class _ProgramSettingsScreenState extends State<ProgramSettingsScreen> {
  late Future<List<Map<String, dynamic>>> _future = _load();

  /// exercise_id → 저장된 개인 설정(없으면 키 자체가 없다).
  Map<String, Map<String, dynamic>> _overrides = const {};

  /// 한 번에 하나만 펼친다 — 운동 5개를 모두 펼치면 폼이 15개가 되어 길을 잃는다.
  String? _expandedId;

  Future<List<Map<String, dynamic>>> _load() async {
    final results = await Future.wait([
      Api.instance.getExercises(),
      Api.instance.getPrograms(),
    ]);
    _overrides = {
      for (final p in results[1].cast<Map<String, dynamic>>())
        p['exercise_id'].toString(): p,
    };
    return results[0].cast<Map<String, dynamic>>();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('운동 프로그램')),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Padding(
              padding: EdgeInsets.all(16),
              child: SkeletonList(itemCount: 4),
            );
          }
          if (snapshot.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: ErrorCard(
                  message: '불러오기 실패: ${snapshot.error}',
                  onRetry: () => setState(() => _future = _load()),
                ),
              ),
            );
          }
          final exercises = snapshot.data ?? const [];
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
            children: [
              _progressionInfoCard(),
              const SizedBox(height: 12),
              if (exercises.isEmpty)
                const EmptyState(
                  icon: Icons.fitness_center,
                  message: '설정할 수 있는 운동이 없습니다.',
                )
              else
                ...exercises.map((e) {
                  final id = e['id'].toString();
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _exerciseCard(id, (e['name'] ?? id).toString()),
                  );
                }),
            ],
          );
        },
      ),
    );
  }

  /// 점진 증가 규칙을 사용자 언어로. 숫자 근거는 `program.py`의
  /// SESSIONS_PER_STEP=3 / MAX_EXTRA_SETS=2 / REPS_PER_STEP=2 / MAX_STEP=4.
  Widget _progressionInfoCard() {
    const style = AppBlocks.tintNavy;
    return BlockCard(
      style: style,
      outlined: true,
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.trending_up_rounded, size: 18, color: AppColors.secondary),
              const SizedBox(width: 8),
              Text('운동량은 이렇게 늘어나요',
                  style: TextStyle(
                      fontSize: 14, fontWeight: FontWeight.w800, color: style.foreground)),
            ],
          ),
          const SizedBox(height: 10),
          for (final line in const [
            '같은 운동을 3세션 할 때마다 한 단계씩 올라갑니다.',
            '먼저 세트를 2세트까지 늘리고, 그다음부터 세트당 횟수를 2회씩 늘려요.',
            '12세션(4단계)을 채우면 자동 증가는 멈춥니다. 더 올리려면 난이도를 올리거나 직접 설정하세요.',
            '휴식 시간은 자동으로 줄지 않습니다 — 피로 관리는 직접 조절하세요.',
          ])
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
                      decoration: const BoxDecoration(
                          color: AppColors.secondary, shape: BoxShape.circle),
                    ),
                  ),
                  Expanded(
                    child: Text(line,
                        style:
                            TextStyle(fontSize: 13, height: 1.5, color: style.mutedOr)),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _exerciseCard(String id, String name) {
    const style = AppBlocks.cream;
    final expanded = _expandedId == id;
    final override = _overrides[id];
    final customFields = override == null
        ? const <String>[]
        : [
            for (final f in const ['sets', 'reps', 'rest_sec'])
              if (override[f] != null) f,
          ];
    final levelOverride = override?['level'] as String?;

    final subtitle = customFields.isEmpty && levelOverride == null
        ? '자동 (프리셋 + 점진 증가)'
        : '직접 설정함'
            '${levelOverride == null ? '' : ' · ${_levelLabels[levelOverride] ?? levelOverride}'}';

    return BlockCard(
      style: style,
      outlined: true, // 딥다크 scaffold 대비 1.10:1 — 경계가 없으면 카드가 사라진다
      padding: const EdgeInsets.all(6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            button: true,
            expanded: expanded,
            label: '$name. $subtitle. ${expanded ? '설정 접기' : '설정 펼치기'}',
            excludeSemantics: true,
            child: InkWell(
              onTap: () => setState(() => _expandedId = expanded ? null : id),
              borderRadius: BorderRadius.circular(16),
              child: Container(
                constraints: const BoxConstraints(minHeight: 48),
                padding: const EdgeInsets.fromLTRB(12, 12, 8, 12),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(name,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w800,
                                  color: style.foreground)),
                          const SizedBox(height: 3),
                          Text(subtitle,
                              style: TextStyle(fontSize: 12, color: style.mutedOr)),
                        ],
                      ),
                    ),
                    Icon(expanded ? Icons.expand_less_rounded : Icons.expand_more_rounded,
                        color: style.mutedOr),
                  ],
                ),
              ),
            ),
          ),
          if (expanded)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
              child: _ProgramEditor(
                // 운동별로 독립된 상태. 저장 후 편집기가 스스로 계획을 다시 읽으므로
                // 부모의 override 갱신으로 위젯을 갈아끼우지 않는다(입력값이 날아간다).
                key: ValueKey(id),
                exerciseId: id,
                initialOverride: override,
                onSaved: (saved) => setState(() {
                  if (saved == null) {
                    _overrides = {..._overrides}..remove(id);
                  } else {
                    _overrides = {..._overrides, id: saved};
                  }
                }),
              ),
            ),
        ],
      ),
    );
  }
}

/// 운동 하나의 설정 폼. 현재 적용 중인 계획(`/me/plan`)을 먼저 보여주고 그 아래에서 덮어쓴다.
class _ProgramEditor extends StatefulWidget {
  final String exerciseId;
  final Map<String, dynamic>? initialOverride;

  /// 저장/초기화 결과를 부모에 알린다. 초기화면 null.
  final ValueChanged<Map<String, dynamic>?> onSaved;

  const _ProgramEditor({
    super.key,
    required this.exerciseId,
    required this.initialOverride,
    required this.onSaved,
  });

  @override
  State<_ProgramEditor> createState() => _ProgramEditorState();
}

class _ProgramEditorState extends State<_ProgramEditor> {
  late Future<Map<String, dynamic>> _planFuture;
  late final TextEditingController _setsCtrl;
  late final TextEditingController _repsCtrl;
  late final TextEditingController _restCtrl;

  String? _level;
  bool _busy = false;

  /// 필드명 → 오류 문구. 저장 시도 시에만 채워진다(입력 중 빨간 글씨로 몰아세우지 않는다).
  Map<String, String?> _errors = const {};

  @override
  void initState() {
    super.initState();
    final o = widget.initialOverride;
    _setsCtrl = TextEditingController(text: o?['sets']?.toString() ?? '');
    _repsCtrl = TextEditingController(text: o?['reps']?.toString() ?? '');
    _restCtrl = TextEditingController(text: o?['rest_sec']?.toString() ?? '');
    _level = o?['level'] as String?;
    _planFuture = _fetchPlan();
  }

  /// 난이도를 아직 고르지 않았으면 서버가 적용 중인 값으로 맞춘다.
  /// build 중 setState를 피하려고 Future 체인에서 미리 채운다.
  Future<Map<String, dynamic>> _fetchPlan() =>
      Api.instance.getPlan(widget.exerciseId).then((p) {
        _planLevel = p['level'] as String?;
        _level ??= _planLevel;
        return p;
      });

  /// 서버가 지금 적용 중인 난이도. 선택값과 다르면 "저장해야 반영된다"고 알린다.
  String? _planLevel;

  @override
  void dispose() {
    _setsCtrl.dispose();
    _repsCtrl.dispose();
    _restCtrl.dispose();
    super.dispose();
  }

  /// 빈 값 = "자동을 따른다"(유효). 숫자가 들어왔다면 백엔드와 같은 범위로 막는다.
  String? _validate(String raw, String field) {
    final text = raw.trim();
    if (text.isEmpty) return null;
    final v = int.tryParse(text);
    if (v == null) return '숫자만 입력해 주세요.';
    final (min, max) = _limits[field]!;
    if (v < min || v > max) return '$min에서 $max 사이로 입력해 주세요.';
    return null;
  }

  int? _parse(TextEditingController c) =>
      c.text.trim().isEmpty ? null : int.parse(c.text.trim());

  void _toast(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _save() async {
    final errors = {
      'sets': _validate(_setsCtrl.text, 'sets'),
      'reps': _validate(_repsCtrl.text, 'reps'),
      'rest_sec': _validate(_restCtrl.text, 'rest_sec'),
    };
    if (errors.values.any((e) => e != null)) {
      setState(() => _errors = errors);
      _toast('입력한 값을 확인해 주세요.');
      return;
    }

    setState(() {
      _errors = const {};
      _busy = true;
    });
    try {
      final saved = await Api.instance.putProgram(
        widget.exerciseId,
        level: _level,
        sets: _parse(_setsCtrl),
        reps: _parse(_repsCtrl),
        restSec: _parse(_restCtrl),
      );
      widget.onSaved(saved);
      if (!mounted) return;
      setState(() => _planFuture = _fetchPlan());
      _toast('저장되었습니다.');
    } catch (e) {
      // 저장에 실패해도 입력값은 그대로 남는다 — 다시 타이핑하게 만들지 않는다.
      _toast('저장 실패: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _reset() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('기본값으로 되돌릴까요?'),
        content: const Text('직접 설정한 난이도·세트·횟수·휴식 시간이 지워지고, 난이도 프리셋과 점진 증가를 다시 따릅니다.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('취소')),
          TextButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text('되돌리기')),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() => _busy = true);
    try {
      // 모든 필드를 null로 보내면 개인 설정이 사라진다(PUT은 행 전체를 대체).
      await Api.instance.putProgram(widget.exerciseId);
      widget.onSaved(null);
      if (!mounted) return;
      setState(() {
        _setsCtrl.clear();
        _repsCtrl.clear();
        _restCtrl.clear();
        _level = null;
        _errors = const {};
        _planFuture = _fetchPlan();
      });
      _toast('기본값으로 되돌렸습니다.');
    } catch (e) {
      _toast('되돌리기 실패: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        FutureBuilder<Map<String, dynamic>>(
          future: _planFuture,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(
                  child: SizedBox(
                      height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2)),
                ),
              );
            }
            if (snapshot.hasError) {
              return ErrorCard(
                message: '현재 적용 중인 계획을 불러오지 못했습니다: ${snapshot.error}',
                onRetry: () => setState(() => _planFuture = _fetchPlan()),
              );
            }
            return _planCard(snapshot.data!);
          },
        ),
        const SizedBox(height: 16),
        _levelSelector(),
        const SizedBox(height: 16),
        _numberField('세트 수', _setsCtrl, 'sets'),
        const SizedBox(height: 12),
        _numberField('세트당 횟수', _repsCtrl, 'reps'),
        const SizedBox(height: 12),
        _numberField('휴식 시간 (초)', _restCtrl, 'rest_sec'),
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: PressScale(
                child: FilledButton(
                  onPressed: _busy ? null : _save,
                  child: _busy
                      ? const SizedBox(
                          height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('저장'),
                ),
              ),
            ),
            const SizedBox(width: 10),
            OutlinedButton(
              onPressed: _busy ? null : _reset,
              style: OutlinedButton.styleFrom(
                minimumSize: const Size(0, 52),
                padding: const EdgeInsets.symmetric(horizontal: 16),
              ),
              child: const Text('기본값'),
            ),
          ],
        ),
      ],
    );
  }

  /// 지금 적용 중인 값 + **그 값이 어디서 왔는지**. `source`/`message`는 서버가 준다.
  Widget _planCard(Map<String, dynamic> plan) {
    const style = AppBlocks.tintGochujang;
    final sets = plan['sets'];
    final reps = plan['reps'];
    final rest = plan['rest_sec'];
    final message = plan['message']?.toString() ?? '';
    final planLevel = plan['level'] as String?;

    // 셋 다 아이콘 + 한국어 라벨을 달고 있다 — 색은 보조 신호일 뿐이다(WCAG 1.4.1).
    final (badgeLabel, badgeIcon, badgeColor) = switch (plan['source']) {
      'custom' => ('내가 설정한 값', Icons.edit_rounded, AppColors.primary),
      'progression' => ('점진 증가로 늘어난 값', Icons.trending_up_rounded, AppColors.secondary),
      _ => ('난이도 기본 프리셋', Icons.tune_rounded, style.mutedOr),
    };

    return BlockCard(
      style: style,
      outlined: true,
      padding: const EdgeInsets.all(16),
      semanticLabel: '지금 적용 중: $sets세트 곱하기 $reps회, 휴식 $rest초. $badgeLabel. $message',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('지금 적용 중',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: style.mutedOr)),
          const SizedBox(height: 6),
          Text('$sets세트 × $reps회',
              style: TextStyle(
                  fontSize: 26, fontWeight: FontWeight.w800, color: style.foreground)),
          const SizedBox(height: 2),
          Text('세트 사이 $rest초 휴식'
              '${planLevel == null ? '' : ' · ${_levelLabels[planLevel] ?? planLevel}'}',
              style: TextStyle(fontSize: 13, color: style.mutedOr)),
          const SizedBox(height: 12),
          // 출처 배지 — 색면을 채우는 대신 테두리로. 미드 그린 채움은 이 카드 위 3:1을
          // 넘기지 못하지만, 테두리로 쓰면 라임 6.59 / 앰버 5.96 / 보조톤 6.39로 전부 통과한다.
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              border: Border.all(color: badgeColor),
              borderRadius: BorderRadius.circular(999),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(badgeIcon, size: 14, color: badgeColor),
                const SizedBox(width: 6),
                Text(badgeLabel,
                    style: TextStyle(
                        fontSize: 12, fontWeight: FontWeight.w700, color: badgeColor)),
              ],
            ),
          ),
          if (message.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(message,
                style: TextStyle(fontSize: 13, height: 1.55, color: style.foreground)),
          ],
        ],
      ),
    );
  }

  Widget _levelSelector() {
    const style = AppBlocks.cream;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('난이도',
            style:
                TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: style.foreground)),
        const SizedBox(height: 8),
        Row(
          children: [
            for (final entry in _levelLabels.entries) ...[
              Expanded(
                child: Semantics(
                  button: true,
                  selected: _level == entry.key,
                  label: '난이도 ${entry.value}',
                  excludeSemantics: true,
                  child: InkWell(
                    onTap: _busy ? null : () => setState(() => _level = entry.key),
                    borderRadius: BorderRadius.circular(12),
                    child: Container(
                      height: 48,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: _level == entry.key ? AppColors.primary : Colors.transparent,
                        borderRadius: BorderRadius.circular(12),
                        // 미선택 테두리는 장식이 아니라 조작 영역 표시 → 카드면 대비 7.25:1.
                        border: Border.all(
                          color: _level == entry.key
                              ? AppColors.primary
                              : AppColors.foregroundMuted,
                        ),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // 선택 상태를 색만으로 알리지 않는다.
                          if (_level == entry.key) ...[
                            const Icon(Icons.check_rounded,
                                size: 16, color: AppColors.onPrimary),
                            const SizedBox(width: 4),
                          ],
                          Text(entry.value,
                              style: TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                                color: _level == entry.key
                                    ? AppColors.onPrimary
                                    : style.foreground,
                              )),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              if (entry.key != _levelLabels.keys.last) const SizedBox(width: 8),
            ],
          ],
        ),
        if (_planLevel != null && _level != null && _level != _planLevel) ...[
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.info_outline_rounded, size: 14, color: AppColors.secondary),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  '선택한 난이도는 저장해야 적용됩니다. 지금은 ${_levelLabels[_planLevel] ?? _planLevel} 기준으로 계산되고 있어요.',
                  style: const TextStyle(
                      fontSize: 12, height: 1.45, color: AppColors.secondary),
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }

  Widget _numberField(String label, TextEditingController controller, String field) {
    final (min, max) = _limits[field]!;
    return TextField(
      controller: controller,
      keyboardType: TextInputType.number,
      enabled: !_busy,
      // 저장 시도 후 고쳤다면 즉시 오류를 걷어준다.
      onChanged: (_) {
        if (_errors[field] != null) setState(() => _errors = {..._errors, field: null});
      },
      decoration: InputDecoration(
        labelText: label,
        errorText: _errors[field],
        helperText: '비워두면 자동 ($min~$max)',
        helperMaxLines: 2,
        errorMaxLines: 2,
      ),
    );
  }
}
