import 'package:flutter/material.dart';
import '../main.dart';
import '../widgets/common.dart';
import 'workout.dart';

/// 운동 가이드 — 색면 카드 4연.
/// navy(히어로) → cream(동작 방법) → crimson(주의사항) → gochujang(CTA).
/// 인접한 두 블록이 같은 색면이 되지 않도록 배치했고, 밝은 면(cream)은 긴 본문을 읽는
/// 한 블록에만 쓴다 — 나머지 셋은 솔리드 채도면이라 크림이 화면을 지배하지 않는다.
class GuideScreen extends StatelessWidget {
  final Map<String, dynamic> exercise;
  const GuideScreen({super.key, required this.exercise});

  @override
  Widget build(BuildContext context) {
    final steps = (exercise['steps'] as List?)?.cast<String>() ?? const [];
    final cautions = (exercise['cautions'] as List?)?.cast<String>() ?? const [];
    final name = exercise['name'] as String? ?? '운동 가이드';

    return Scaffold(
      appBar: AppBar(title: Text(name)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          _hero(name, steps.length),
          const SizedBox(height: 12),
          _stepsBlock(steps),
          const SizedBox(height: 12),
          _cautionsBlock(cautions),
          const SizedBox(height: 20),
          _startCta(context),
        ],
      ),
    );
  }

  // --- 1. 히어로 색면(navy): 운동 이름 + 단계 수 거대 숫자 + 부위/난이도 메타. ---
  Widget _hero(String name, int stepCount) {
    const s = AppBlocks.navy;
    return BlockCard(
      style: s,
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
          const SizedBox(height: 6),
          Text(
            name,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800, height: 1.2),
          ),
          const SizedBox(height: 18),
          BigStat(
            style: s,
            value: stepCount == 0 ? '-' : '$stepCount',
            unit: '단계',
            caption: '동작 순서',
            size: 60,
          ),
          const SizedBox(height: 18),
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

  /// 히어로 안쪽 메타 — 색면 위 알파 채움. 라벨을 항상 병기해 값의 의미가 색/아이콘에만
  /// 의존하지 않게 한다.
  Widget _metaChip(BlockStyle s, IconData icon, String label, String value) {
    return Semantics(
      label: '$label $value',
      container: true,
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: s.foreground.withValues(alpha: 0.12),
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

  // --- 2. 동작 방법(cream 색면): 번호 배지를 고추장 솔리드로 찍어 리듬을 만든다. ---
  Widget _stepsBlock(List<String> steps) {
    const s = AppBlocks.cream;
    if (steps.isEmpty) {
      return const BlockCard(
        style: s,
        outlined: true,
        child: EmptyState(
          icon: Icons.checklist_rounded,
          message: '등록된 단계 설명이 없습니다.',
          compact: true,
        ),
      );
    }
    return BlockCard(
      style: s,
      // 크림은 scaffold와 1.05:1 → 아웃라인이 없으면 카드 면 자체가 보이지 않는다.
      outlined: true,
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _blockTitle(s, Icons.checklist_rounded, '동작 방법', '${steps.length}단계'),
          const SizedBox(height: 16),
          for (var i = 0; i < steps.length; i++) _stepRow(s, i, steps[i], i == steps.length - 1),
        ],
      ),
    );
  }

  Widget _stepRow(BlockStyle s, int index, String text, bool isLast) {
    return Semantics(
      label: '${index + 1}단계. $text',
      container: true,
      excludeSemantics: true,
      child: Column(
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 30,
                height: 30,
                alignment: Alignment.center,
                decoration: const BoxDecoration(
                  color: AppColors.primary, // Gochujang 색면 배지 — 위 텍스트 10.36:1
                  shape: BoxShape.circle,
                ),
                child: Text(
                  '${index + 1}',
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    color: AppColors.onPrimary, // Varden — 고추장 위 10.36:1
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(text, style: const TextStyle(fontSize: 15, height: 1.5)),
                ),
              ),
            ],
          ),
          if (!isLast)
            Padding(
              padding: const EdgeInsets.fromLTRB(42, 12, 0, 12),
              child: Container(height: 1, color: s.foreground.withValues(alpha: 0.10)),
            )
          else
            const SizedBox(height: 10),
        ],
      ),
    );
  }

  // --- 3. 주의사항(crimson 색면): 경고의 의미를 색면으로. 색 단독 전달 금지라
  //        블록 제목·행마다 경고 아이콘과 텍스트를 병기한다. ---
  Widget _cautionsBlock(List<String> cautions) {
    const s = AppBlocks.crimson;
    if (cautions.isEmpty) {
      return const BlockCard(
        style: AppBlocks.cream,
        outlined: true,
        child: EmptyState(
          icon: Icons.warning_amber_rounded,
          message: '등록된 주의사항이 없습니다.',
          compact: true,
        ),
      );
    }
    return BlockCard(
      style: s,
      semanticLabel: '주의사항 ${cautions.length}개. ${cautions.join(' ')}',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // crimson은 muted가 없다 → 제목/본문/트레일링 모두 단일 크림 톤.
          _blockTitle(s, Icons.warning_amber_rounded, '주의사항', '${cautions.length}개'),
          const SizedBox(height: 14),
          for (var i = 0; i < cautions.length; i++) ...[
            if (i > 0) const SizedBox(height: 12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.error_outline_rounded, size: 18, color: s.foreground),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(cautions[i],
                      style: const TextStyle(fontSize: 14, height: 1.5)),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  // --- 4. CTA(gochujang 색면): 화면에서 가장 중요한 액션 → 버튼이 아니라 색면 블록. ---
  Widget _startCta(BuildContext context) {
    const s = AppBlocks.gochujang;
    return PressScale(
      child: BlockCard(
        style: s,
        radius: 22,
        padding: const EdgeInsets.all(16),
        semanticLabel: '운동 시작',
        onTap: () => Navigator.of(context)
            .push(fadeRoute(context, (_) => WorkoutScreen(exercise: exercise))),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: s.foreground.withValues(alpha: 0.16),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Icon(Icons.play_arrow_rounded, size: 28, color: s.foreground),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text('운동 시작',
                      style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 3),
                  Text('가이드를 확인했다면 바로 시작하세요',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 12, color: s.mutedOr)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Icon(Icons.arrow_forward_rounded, size: 22, color: s.foreground),
          ],
        ),
      ),
    );
  }

  Widget _blockTitle(BlockStyle s, IconData icon, String title, String trailing) {
    return Row(
      children: [
        Icon(icon, size: 20, color: s.foreground),
        const SizedBox(width: 8),
        Expanded(
          child: Text(title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
        ),
        Text(trailing, style: TextStyle(fontSize: 12, color: s.mutedOr)),
      ],
    );
  }
}
