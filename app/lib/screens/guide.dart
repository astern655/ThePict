import 'package:flutter/material.dart';
import '../main.dart';
import '../widgets/common.dart';
import 'workout.dart';

/// 운동 가이드 — 시안 레이아웃: 원형 뒤로가기 + 큰 타이틀 + 글라스 히어로 + 흰 카드(동작/주의) + 코랄 CTA.
/// 코랄은 화면에서 '운동 시작' 채움 + 큰 숫자·번호 darken 코랄에만 쓴다. 주의사항은 앰버로 구분한다.
class GuideScreen extends StatelessWidget {
  final Map<String, dynamic> exercise;
  const GuideScreen({super.key, required this.exercise});

  @override
  Widget build(BuildContext context) {
    final steps = (exercise['steps'] as List?)?.cast<String>() ?? const [];
    final cautions = (exercise['cautions'] as List?)?.cast<String>() ?? const [];
    final name = exercise['name'] as String? ?? '운동 가이드';

    // 시안: 내비 바 없이 본문 최상단에 원형 뒤로가기 + 운동 이름 큰 타이틀(iOS 26 large-title).
    return GradientBackground(
      child: Scaffold(
        backgroundColor: Colors.transparent,
        body: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
            children: [
              _backButton(context),
              const SizedBox(height: 14),
              _largeTitle(name),
              _hero(steps.length),
              const SizedBox(height: 20),
              _stepsBlock(steps),
              const SizedBox(height: 20),
              _cautionsBlock(cautions),
              const SizedBox(height: 24),
              _startCta(context),
            ],
          ),
        ),
      ),
    );
  }

  /// 시안 원형 뒤로가기 — 흰 면 + chevron. IconButton으로 최소 48 터치·툴팁 확보.
  Widget _backButton(BuildContext context) => Align(
        alignment: Alignment.centerLeft,
        child: IconButton(
          onPressed: () => Navigator.of(context).maybePop(),
          tooltip: '뒤로',
          icon: const Icon(Icons.chevron_left_rounded),
          style: IconButton.styleFrom(
            backgroundColor: AppColors.surface,
            foregroundColor: AppColors.foreground,
            shape: const CircleBorder(side: BorderSide(color: AppColors.border)),
            minimumSize: const Size(44, 44),
          ),
        ),
      );

  /// iOS 큰 타이틀 — 34px bold 좌측. 코랄은 채움 전용이라 여기 안 쓴다.
  Widget _largeTitle(String text) => Padding(
        padding: const EdgeInsets.only(left: 4, top: 0, bottom: 18),
        child: Semantics(
          header: true,
          child: Text(
            text,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
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

  // --- 1. 메타 히어로(포컬): 단계 수 darken 코랄 거대 숫자 + 부위/난이도. ---
  Widget _hero(int stepCount) {
    // 흰 카드 위 텍스트 토큰 — cream 슬롯(ink 전경 + 라이트 muted)을 재사용한다.
    const s = AppBlocks.cream;
    return GlassCard(
      padding: const EdgeInsets.fromLTRB(22, 20, 22, 22),
      radius: 26,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.menu_book_rounded, size: 18, color: s.mutedOr),
              const SizedBox(width: 8),
              Text('운동 가이드',
                  style:
                      TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: s.mutedOr)),
            ],
          ),
          const SizedBox(height: 14),
          BigStat(
            style: s,
            // 시안은 큰 숫자를 darken — 흰 카드 위 primaryText(#C63D22, 5.13:1).
            valueColor: AppColors.primaryText,
            value: stepCount == 0 ? '-' : '$stepCount',
            unit: '단계',
            caption: '동작 순서',
            size: 56,
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _metaChip(
                  s,
                  Icons.my_location_rounded,
                  '부위',
                  exercise['target'] as String? ?? '-',
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _metaChip(
                  s,
                  Icons.speed_rounded,
                  '난이도',
                  exercise['difficulty'] as String? ?? '-',
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// 히어로 안쪽 메타 — 시안 rgba(28,43,46,.08) 채움. 라벨을 항상 병기해 색/아이콘 단독 의존 방지.
  Widget _metaChip(BlockStyle s, IconData icon, String label, String value) {
    return Semantics(
      label: '$label $value',
      container: true,
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: s.foreground.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Row(
          children: [
            Icon(icon, size: 16, color: s.foreground),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(label, style: TextStyle(fontSize: 11, color: s.mutedOr)),
                  const SizedBox(height: 2),
                  Text(
                    value,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  // --- 2. 동작 방법(흰 카드): 시안 — 번호(darken 코랄) + 본문. 원형 배지·구분선 없이 여백으로 리듬. ---
  Widget _stepsBlock(List<String> steps) {
    if (steps.isEmpty) {
      return const GlassCard(
        child: EmptyState(
          icon: Icons.checklist_rounded,
          message: '등록된 단계 설명이 없습니다.',
          compact: true,
        ),
      );
    }
    return GlassCard(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _blockTitle(Icons.checklist_rounded, '동작 방법', '${steps.length}단계'),
          for (var i = 0; i < steps.length; i++) _numberedRow(i + 1, steps[i], AppColors.primaryText),
        ],
      ),
    );
  }

  // --- 3. 주의사항(흰 카드 + 앰버): 시안 — 번호·본문 모두 앰버. 제목 '주의사항'이 의미를 못 박아
  //        색 단독 전달이 아니다(WCAG 1.4.1). ---
  Widget _cautionsBlock(List<String> cautions) {
    const accent = AppColors.secondary; // 앰버 — 흰 카드 위 5.02:1 AA, 주의(caution) 톤
    if (cautions.isEmpty) {
      return const GlassCard(
        child: EmptyState(
          icon: Icons.warning_amber_rounded,
          message: '등록된 주의사항이 없습니다.',
          compact: true,
        ),
      );
    }
    return GlassCard(
      padding: const EdgeInsets.all(18),
      semanticLabel: '주의사항 ${cautions.length}개. ${cautions.join(' ')}',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _blockTitle(Icons.warning_amber_rounded, '주의사항', '${cautions.length}개',
              accent: accent),
          for (var i = 0; i < cautions.length; i++)
            _numberedRow(i + 1, cautions[i], accent, textColor: accent, bold: true),
        ],
      ),
    );
  }

  /// 시안 번호 행 — 22px 폭 번호(center) + 본문. 단계/주의 공용.
  Widget _numberedRow(int n, String text, Color numberColor,
      {Color? textColor, bool bold = false}) {
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Semantics(
        label: '$n. $text',
        container: true,
        excludeSemantics: true,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 22,
              child: Text(
                '$n',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                  color: numberColor,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                text,
                style: TextStyle(
                  fontSize: 15,
                  height: 1.5,
                  fontWeight: bold ? FontWeight.w600 : FontWeight.w400,
                  color: textColor ?? AppColors.foreground,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // --- 4. CTA: 화면에서 가장 중요한 액션 → 솔리드 코랄 채움 GradientButton. ---
  Widget _startCta(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        GradientButton(
          icon: Icons.play_arrow_rounded,
          onPressed: () => Navigator.of(context)
              .push(fadeRoute(context, (_) => WorkoutScreen(exercise: exercise))),
          child: const Text('운동 시작'),
        ),
        const SizedBox(height: 10),
        const Text(
          '가이드를 확인했다면 바로 시작하세요',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 12, color: AppColors.foregroundMuted),
        ),
      ],
    );
  }

  Widget _blockTitle(IconData icon, String title, String trailing, {Color? accent}) {
    final c = accent ?? AppColors.foreground;
    return Row(
      children: [
        Icon(icon, size: 20, color: c),
        const SizedBox(width: 8),
        Expanded(
          child: Text(title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: c)),
        ),
        Text(trailing,
            style: const TextStyle(fontSize: 12, color: AppColors.foregroundMuted)),
      ],
    );
  }
}
