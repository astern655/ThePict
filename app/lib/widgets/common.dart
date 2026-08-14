import 'dart:math';

import 'package:flutter/material.dart';
import '../main.dart';

/// 폼 점수 구간 색상 규칙 — 80↑ success(틸/green good), 60↑ secondary(앰버 mid), 미만 error(레드 bad).
/// 세 색이 서로 구분되어야 하므로 브랜드 코랄(primary)과 겹치지 않게 잡았다: good=틸, mid=앰버,
/// bad=크림슨 레드(코랄보다 더 붉은 톤). dark: true는 트루 블랙 몰입 화면(workout)용 — 값이 다르다.
/// 라이트(흰 카드) 검증: 5.47 / 5.02 / 6.29:1, 라이트(scaffold) 4.90 / 4.50 / 5.63:1,
/// 다크(검정) 7.90 / 12.58 / 7.59:1 — 전부 4.5:1 이상. (색만으로 전달 금지 → formScoreIcon 병행)
Color formScoreColor(num score, {bool dark = false}) {
  if (score >= 80) return dark ? AppDark.success : AppColors.success;
  if (score >= 60) return dark ? AppDark.secondary : AppColors.secondary;
  return dark ? AppDark.error : AppColors.error;
}

/// 색만으로 구간을 전달하지 않기 위한 짝 아이콘 (WCAG 1.4.1).
IconData formScoreIcon(num score) {
  if (score >= 80) return Icons.check_circle_rounded;
  if (score >= 60) return Icons.error_outline_rounded;
  return Icons.warning_amber_rounded;
}

// ---------------------------------------------------------------------------
// 플랫 iOS 프리미티브 — 시안 기반 기반(화면팀 조립용). (크리스탈 글라스에서 전환)
//   * GradientBackground : scaffold를 감싸는 단색 배경(오프화이트 / 트루블랙). 그라데이션 없음.
//   * GlassCard          : 플랫 흰 카드(#FFF + 얇은 보더 + 미세 그림자). 블러 없음. 이름 유지.
//   * GradientButton     : 솔리드 코랄 필(pill) CTA + 다크 잉크 텍스트.
// 반복 아이템 색면은 솔리드 [BlockCard]가 담당한다.
// ---------------------------------------------------------------------------

/// 단색 배경. 화면 Scaffold를 감싸 쓴다:
///   `GradientBackground(child: Scaffold(backgroundColor: Colors.transparent, ...))`
/// 플랫 전환 후 그라데이션을 쓰지 않는다 — 오프화이트(라이트) / 트루블랙(workout) 단색을 칠한다.
/// [gradient] 파라미터는 시그니처 호환용으로 남기되 **무시**한다(플랫 배경엔 그라데이션이 없다).
class GradientBackground extends StatelessWidget {
  final Widget child;

  /// 트루 블랙 몰입 화면(workout)에서 true.
  final bool dark;

  /// (레거시) 무시됨 — 플랫 배경은 단색이다. 시그니처 호환용으로만 남긴다.
  final Gradient? gradient;

  const GradientBackground({
    super.key,
    required this.child,
    this.dark = false,
    this.gradient,
  });

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: dark ? AppDark.scaffold : AppColors.scaffold,
      child: child,
    );
  }
}

/// 플랫 흰 카드 — 시안 기준 `#FFF` + 얇은 헤어라인 보더 + 미세 그림자(라이트 0 1px 2px rgba .04).
/// (크리스탈 글라스에서 전환: BackdropFilter 블러 제거. 이름·시그니처는 화면 9개가 참조하므로 유지.)
///
/// **대비**: 표면 = 흰색 #FFFFFF → 위 ink 14.64:1 AAA. 텍스트/아이콘은 **어두운 잉크**
/// ([AppColors.foreground])를 상속받는다.
class GlassCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final double radius;

  /// (레거시) 무시됨 — 플랫 카드엔 블러가 없다. 시그니처 호환용으로만 남긴다.
  final double blur;

  /// 지정 시 전체가 눌리는 카드(잉크 리플 + 포커스 + 최소 48px).
  final VoidCallback? onTap;

  /// 스크린리더용 요약.
  final String? semanticLabel;

  /// 트루 블랙 몰입 화면(workout)에서 true — 다크 카드면.
  final bool dark;

  const GlassCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(18),
    this.radius = 22,
    this.blur = 18,
    this.onTap,
    this.semanticLabel,
    this.dark = false,
  });

  @override
  Widget build(BuildContext context) {
    final br = BorderRadius.circular(radius);
    final surface = dark ? AppDark.surface : AppColors.surface;
    final borderColor = dark ? AppDark.border : AppColors.border;
    final fg = dark ? AppDark.foreground : AppColors.foreground;
    // 시안 라이트 카드 그림자 = 0 1px 2px rgba(28,43,46,.04). 다크는 순검정 미세 그림자.
    final shadow = dark
        ? const Color(0x66000000)
        : const Color(0x0A1C2B2E);

    Widget content = DefaultTextStyle.merge(
      style: TextStyle(color: fg),
      child: IconTheme.merge(
        data: IconThemeData(color: fg),
        child: Padding(padding: padding, child: child),
      ),
    );

    content = Material(
      color: Colors.transparent,
      child: onTap == null
          ? content
          : InkWell(
              onTap: onTap,
              customBorder: RoundedRectangleBorder(borderRadius: br),
              splashColor: fg.withValues(alpha: 0.10),
              highlightColor: fg.withValues(alpha: 0.05),
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 48),
                child: content,
              ),
            ),
    );

    Widget card = DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: br,
        border: Border.all(color: borderColor, width: 1),
        boxShadow: [
          BoxShadow(color: shadow, blurRadius: dark ? 12 : 2, offset: const Offset(0, 1)),
        ],
      ),
      child: ClipRRect(borderRadius: br, child: content),
    );

    if (semanticLabel != null) {
      card = Semantics(label: semanticLabel, container: true, child: card);
    }
    return card;
  }
}

/// 솔리드 코랄 필(pill) CTA. FilledButton 테마와 별개로 아이콘 행·[PressScale]가 필요할 때 이 위젯으로.
/// 채움 위 텍스트/아이콘은 **어두운 잉크**([AppColors.onPrimary] #26120B, coral 위 5.95:1 AA).
/// 시안 CTA와 동일한 필 형태(radius 26+). 최소 높이 52, 최소 터치 48↑, 포커스 링, [PressScale], reduced-motion 존중.
class GradientButton extends StatelessWidget {
  final VoidCallback? onPressed;

  /// 보통 Text. 색은 잉크로 자동 상속되므로 지정 불필요.
  final Widget child;
  final IconData? icon;

  /// 채움. 기본 [AppGradients.coral](솔리드 코랄 coral_mid). 위 텍스트/아이콘은 잉크여야 한다.
  final Gradient gradient;
  final double minHeight;

  const GradientButton({
    super.key,
    required this.onPressed,
    required this.child,
    this.icon,
    this.gradient = AppGradients.coral,
    this.minHeight = 52,
  });

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    const ink = AppColors.onPrimary; // 밝은 코랄 채움 위 어두운 잉크(#26120B, 5.95:1)
    final radius = BorderRadius.circular(999); // 필(pill) — 시안 CTA

    final label = DefaultTextStyle.merge(
      style: const TextStyle(color: ink, fontWeight: FontWeight.w700, fontSize: 16),
      child: IconTheme.merge(
        data: const IconThemeData(color: ink, size: 20),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[Icon(icon), const SizedBox(width: 8)],
            Flexible(child: child),
          ],
        ),
      ),
    );

    final button = Opacity(
      opacity: enabled ? 1 : 0.5,
      child: DecoratedBox(
        decoration: BoxDecoration(gradient: gradient, borderRadius: radius),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onPressed,
            borderRadius: radius,
            splashColor: ink.withValues(alpha: 0.10),
            highlightColor: ink.withValues(alpha: 0.06),
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: minHeight),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                child: Center(child: label),
              ),
            ),
          ),
        ),
      ),
    );

    return Semantics(
      button: true,
      enabled: enabled,
      child: PressScale(child: button),
    );
  }
}

/// 빈 상태 공통 위젯 — 아이콘 + 한 줄 안내 + 선택적 행동 버튼.
class EmptyState extends StatelessWidget {
  final IconData icon;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;
  final bool compact;

  /// 트루 블랙 몰입 화면(workout)에서 쓸 때 true. 기본 false는 일반 딥다크 화면용.
  final bool dark;

  const EmptyState({
    super.key,
    required this.icon,
    required this.message,
    this.actionLabel,
    this.onAction,
    this.compact = false,
    this.dark = false,
  });

  @override
  Widget build(BuildContext context) {
    final muted = dark ? AppDark.foregroundMuted : AppColors.foregroundMuted;
    return Padding(
      padding: EdgeInsets.symmetric(vertical: compact ? 12 : 32, horizontal: 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: muted, size: compact ? 28 : 40),
          const SizedBox(height: 10),
          Text(message,
              textAlign: TextAlign.center,
              style: TextStyle(color: muted, fontSize: 13)),
          if (actionLabel != null && onAction != null) ...[
            const SizedBox(height: 14),
            OutlinedButton(onPressed: onAction, child: Text(actionLabel!)),
          ],
        ],
      ),
    );
  }
}

/// 인라인 에러 카드 — 메시지 + 재시도 버튼. (기존 홈 에러 상태 공통화)
class ErrorCard extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  /// 트루 블랙 몰입 화면(workout)에서 쓸 때 true. 기본 false는 일반 딥다크 화면용.
  final bool dark;

  const ErrorCard({
    super.key,
    required this.message,
    required this.onRetry,
    this.dark = false,
  });

  @override
  Widget build(BuildContext context) {
    final muted = dark ? AppDark.foregroundMuted : AppColors.foregroundMuted;
    final error = dark ? AppDark.error : AppColors.error;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.error_outline, color: error, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(message, style: TextStyle(color: muted, fontSize: 13)),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerRight,
              child: OutlinedButton(onPressed: onRetry, child: const Text('다시 시도')),
            ),
          ],
        ),
      ),
    );
  }
}

/// 홈 카드 리스트 로딩 스켈레톤 — surfaceMuted 배경 + 미세 shimmer.
/// reduced-motion 시 정적 배경만 표시.
class SkeletonList extends StatefulWidget {
  final int itemCount;

  /// 트루 블랙 몰입 화면(workout)에서 쓸 때 true. false(기본)는 일반 딥다크 화면용.
  final bool dark;
  const SkeletonList({super.key, this.itemCount = 4, this.dark = false});

  @override
  State<SkeletonList> createState() => _SkeletonListState();
}

class _SkeletonListState extends State<SkeletonList> with SingleTickerProviderStateMixin {
  late final AnimationController _controller =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1100));
  bool _reduceMotion = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _reduceMotion = MediaQuery.of(context).disableAnimations;
    if (_reduceMotion) {
      _controller.stop();
    } else if (!_controller.isAnimating) {
      _controller.repeat();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: widget.itemCount,
      separatorBuilder: (_, __) => const SizedBox(height: 12),
      itemBuilder: (context, index) =>
          _SkeletonCard(controller: _reduceMotion ? null : _controller, dark: widget.dark),
    );
  }
}

class _SkeletonCard extends StatelessWidget {
  final AnimationController? controller;
  final bool dark;
  const _SkeletonCard({required this.controller, required this.dark});

  @override
  Widget build(BuildContext context) {
    final track = dark ? AppDark.surfaceMuted : AppColors.surfaceMuted;
    // 전면 다크가 되면서 기존 sheen(border/surface)이 track보다 **어두워져** shimmer가
    // 반대로 흘렀다. 전경색을 옅게 얹어 항상 track보다 밝은 하이라이트를 보장한다.
    final sheen = (dark ? AppDark.foreground : AppColors.foreground).withValues(alpha: 0.08);
    final base = Container(
      height: 80,
      decoration: BoxDecoration(
        color: track,
        borderRadius: BorderRadius.circular(18),
      ),
    );
    final c = controller;
    if (c == null) return base;
    return AnimatedBuilder(
      animation: c,
      child: base,
      builder: (context, child) => ShaderMask(
        blendMode: BlendMode.srcATop,
        shaderCallback: (rect) => LinearGradient(
          colors: [track, sheen, track],
          stops: const [0.35, 0.5, 0.65],
          begin: Alignment(-1 - c.value * 2, 0),
          end: Alignment(1 - c.value * 2, 0),
        ).createShader(rect),
        child: child,
      ),
    );
  }
}

/// 주요 CTA 프레스 피드백 — 0.97 스케일 다운 80ms. reduced-motion 시 스케일 생략.
class PressScale extends StatefulWidget {
  final Widget child;
  const PressScale({super.key, required this.child});

  @override
  State<PressScale> createState() => _PressScaleState();
}

class _PressScaleState extends State<PressScale> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    return Listener(
      onPointerDown: (_) => setState(() => _pressed = true),
      onPointerUp: (_) => setState(() => _pressed = false),
      onPointerCancel: (_) => setState(() => _pressed = false),
      child: AnimatedScale(
        scale: !reduceMotion && _pressed ? 0.97 : 1.0,
        duration: const Duration(milliseconds: 80),
        child: widget.child,
      ),
    );
  }
}

/// 최근 폼 점수 스파크라인 — CustomPaint 기반, 패키지 추가 없이 구현.
class FormScoreSparkline extends StatelessWidget {
  final List<num> scores; // 오래된 → 최근 순
  const FormScoreSparkline({super.key, required this.scores});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: scores.isEmpty
          ? '최근 폼 점수 추이 없음'
          : '최근 폼 점수 추이, 최근값 ${scores.last.round()}점',
      child: SizedBox(
        height: 48,
        width: double.infinity,
        child: CustomPaint(painter: _SparklinePainter(scores: scores)),
      ),
    );
  }
}

class _SparklinePainter extends CustomPainter {
  final List<num> scores;
  const _SparklinePainter({required this.scores});

  @override
  void paint(Canvas canvas, Size size) {
    if (scores.length < 2) return;
    final dx = size.width / (scores.length - 1);
    final points = <Offset>[
      for (var i = 0; i < scores.length; i++)
        Offset(dx * i, size.height - (scores[i] / 100).clamp(0, 1) * size.height),
    ];

    final linePaint = Paint()
      ..color = AppColors.primary.withValues(alpha: 0.7)
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    final path = Path()..moveTo(points.first.dx, points.first.dy);
    for (final p in points.skip(1)) {
      path.lineTo(p.dx, p.dy);
    }
    canvas.drawPath(path, linePaint);

    for (var i = 0; i < points.length; i++) {
      canvas.drawCircle(points[i], 3, Paint()..color = formScoreColor(scores[i]));
    }
  }

  @override
  bool shouldRepaint(covariant _SparklinePainter oldDelegate) => oldDelegate.scores != scores;
}

// ---------------------------------------------------------------------------
// 색면(color-block) 빌딩블록 — 60-30-10의 "30".
// 전부 [BlockStyle]을 주입받는다. 배경/전경이 한 벌로 오므로 라이트·다크 양쪽에서 동일하게 쓴다.
// ---------------------------------------------------------------------------

/// 색면 카드의 기본 단위. 카드 면 **전체**를 [style].background로 칠하고,
/// 내부 텍스트·아이콘 색을 [style].foreground로 자동 상속시킨다.
/// 개별 자식이 색을 다시 지정할 필요가 없다 — 그게 이 위젯의 존재 이유다.
class BlockCard extends StatelessWidget {
  final BlockStyle style;
  final Widget child;
  final EdgeInsetsGeometry padding;
  final double radius;

  /// 지정 시 전체가 눌리는 카드가 된다(잉크 리플 + 키보드 포커스 + 최소 48px 높이).
  final VoidCallback? onTap;

  /// 스크린리더용 요약. 내부에 숫자·차트가 흩어져 있을 때 한 문장으로 묶어준다.
  final String? semanticLabel;

  /// 크림 배경 위 소프트 틴트처럼 배경 대비가 낮은 조합에서 카드 경계를 살릴 때 true.
  final bool outlined;

  const BlockCard({
    super.key,
    required this.style,
    required this.child,
    this.padding = const EdgeInsets.all(18),
    this.radius = 22,
    this.onTap,
    this.semanticLabel,
    this.outlined = false,
  });

  @override
  Widget build(BuildContext context) {
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(radius),
      // 전경색@0.55를 scaffold(#F2F2F7) 위에 합성한 보더가 scaffold 대비 3:1을 넘어야 한다(1.4.11).
      // outlined는 배경이 scaffold와 가까운 옅은 슬롯에서만 켠다 — 그 슬롯은 전경이 어두워
      // 합성 결과: cream 3.73 / tintNavy 3.73 / tintGochujang 3.73 / tintCrimson 3.17 /
      // navy 3.73 / crimson 3.98 — 전부 ≥3. (gochujang 코랄 솔리드는 자체로 분리돼 outlined 미사용)
      side: outlined
          ? BorderSide(color: style.foreground.withValues(alpha: 0.55), width: 1)
          : BorderSide.none,
    );

    Widget content = DefaultTextStyle.merge(
      style: TextStyle(color: style.foreground),
      child: IconTheme.merge(
        data: IconThemeData(color: style.foreground),
        child: Padding(padding: padding, child: child),
      ),
    );

    if (onTap != null) {
      content = InkWell(
        onTap: onTap,
        customBorder: shape,
        // 솔리드 색면 위에서는 기본 리플이 보이지 않는다 → 전경색에서 뽑아 쓴다.
        splashColor: style.foreground.withValues(alpha: 0.12),
        highlightColor: style.foreground.withValues(alpha: 0.06),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 48),
          child: content,
        ),
      );
    }

    final card = Material(
      color: style.background,
      shape: shape,
      clipBehavior: Clip.antiAlias,
      child: content,
    );

    if (semanticLabel == null) return card;
    return Semantics(label: semanticLabel, container: true, child: card);
  }
}

/// 숫자 하나 + 라벨 하나짜리 색면 배지. 3연으로 나열하는 용도(예: 53.5kg / 50kg / 740kcal).
class StatPill extends StatelessWidget {
  final BlockStyle style;
  final String value;
  final String? unit;
  final String label;
  final IconData? icon;

  /// Row에서 Expanded로 감싸 균등 분할할 때 텍스트를 가운데로.
  final bool center;

  /// 크림/틴트처럼 scaffold와 배경 대비가 낮은 색면일 때 경계를 살린다.
  /// cream 필은 크림 scaffold 위 1.07:1이라 이게 없으면 카드 면이 사라진다.
  final bool outlined;

  const StatPill({
    super.key,
    required this.style,
    required this.value,
    required this.label,
    this.unit,
    this.icon,
    this.center = false,
    this.outlined = false,
  });

  @override
  Widget build(BuildContext context) {
    final align = center ? CrossAxisAlignment.center : CrossAxisAlignment.start;
    return BlockCard(
      style: style,
      radius: 20,
      outlined: outlined,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      semanticLabel: '$label $value${unit ?? ''}',
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: align,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 18, color: style.mutedOr),
            const SizedBox(height: 6),
          ],
          Row(
            mainAxisSize: MainAxisSize.min,
            textBaseline: TextBaseline.alphabetic,
            crossAxisAlignment: CrossAxisAlignment.baseline,
            children: [
              Flexible(
                child: Text(
                  value,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w800,
                    height: 1.05,
                    fontFeatures: [FontFeature.tabularFigures()],
                  ),
                ),
              ),
              if (unit != null) ...[
                const SizedBox(width: 2),
                Text(unit!,
                    style: TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w700, color: style.mutedOr)),
              ],
            ],
          ),
          const SizedBox(height: 2),
          Text(
            label,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            textAlign: center ? TextAlign.center : TextAlign.start,
            style: TextStyle(fontSize: 12, height: 1.25, color: style.mutedOr),
          ),
        ],
      ),
    );
  }
}

/// 히어로 카드 안에 들어가는 거대 숫자. 단위는 작게 baseline 정렬, 캡션은 아래.
/// [BlockCard]를 감싸지 않는다 — 이미 색면인 카드 **안에** 놓이는 조각이다.
class BigStat extends StatelessWidget {
  final BlockStyle style;
  final String value;
  final String? unit;
  final String? caption;
  final double size;

  /// 지정 시 큰 숫자를 이 솔리드 색으로 칠한다. 히어로 focal 숫자엔 코랄([AppColors.primary])을
  /// 넘긴다 — coral_deep은 밝은 글라스(#FFF7F3) 위 3.98:1로 큰 텍스트(3:1) 통과. 미지정 시
  /// style.foreground(잉크)로 조용히 떨어진다. **작은(≤24px) 숫자엔 코랄을 넘기지 말 것(대비 미달).**
  final Color? valueColor;

  /// 지정 시 큰 숫자를 이 그라데이션 색으로 칠한다(ShaderMask). 현재 화면에선 미사용 — 산호↔청록
  /// 브랜드 그라데이션을 걷어내고 솔리드([valueColor])로 통일했다. 훅만 남겨둔다.
  final Gradient? gradient;

  const BigStat({
    super.key,
    required this.style,
    required this.value,
    this.unit,
    this.caption,
    this.size = 56,
    this.valueColor,
    this.gradient,
  });

  Widget _maybeGradient(Widget text) {
    final g = gradient;
    if (g == null) return text;
    return ShaderMask(
      blendMode: BlendMode.srcIn,
      shaderCallback: (rect) => g.createShader(rect),
      child: text,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '${caption ?? ''} $value${unit ?? ''}'.trim(),
      container: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            textBaseline: TextBaseline.alphabetic,
            crossAxisAlignment: CrossAxisAlignment.baseline,
            children: [
              Flexible(
                child: _maybeGradient(
                  Text(
                    value,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: size,
                      fontWeight: FontWeight.w800,
                      height: 1.0,
                      letterSpacing: -1.5,
                      // gradient가 있으면 ShaderMask(srcIn)가 색을 대체하므로 흰색 베이스.
                      // 아니면 valueColor(코랄 등 솔리드) → 없으면 style.foreground(잉크).
                      color: gradient != null ? Colors.white : (valueColor ?? style.foreground),
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                ),
              ),
              if (unit != null) ...[
                const SizedBox(width: 4),
                Padding(
                  padding: EdgeInsets.only(bottom: size * 0.08),
                  child: Text(unit!,
                      style: TextStyle(
                          fontSize: size * 0.28,
                          fontWeight: FontWeight.w700,
                          color: style.mutedOr)),
                ),
              ],
            ],
          ),
          if (caption != null) ...[
            const SizedBox(height: 6),
            Text(caption!,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 13, height: 1.3, color: style.mutedOr)),
          ],
        ],
      ),
    );
  }
}

/// 값 리스트 → 세로 막대. 세트별 기록·주간 볼륨용. 색면 카드 안에 놓는 전제.
/// 축이 없으므로 값을 읽을 수 있게 [showValues] 또는 [labels]를 켜라(색만으로 정보 전달 금지).
class MiniBarChart extends StatelessWidget {
  final List<num> values;
  final BlockStyle style;

  /// 막대 아래 라벨. values와 길이가 다르면 짧은 쪽까지만 그린다.
  final List<String>? labels;

  /// 막대 위에 값 숫자를 얹는다.
  final bool showValues;

  /// null이면 values의 최댓값을 기준으로 정규화.
  final num? maxValue;

  /// 특정 인덱스를 강조(예: 오늘). 나머지는 반투명.
  final int? highlightIndex;

  final double height;

  /// 스크린리더용 요약 — 막대는 그림이라 읽히지 않는다.
  final String semanticLabel;

  const MiniBarChart({
    super.key,
    required this.values,
    required this.style,
    required this.semanticLabel,
    this.labels,
    this.showValues = false,
    this.maxValue,
    this.highlightIndex,
    this.height = 96,
  });

  @override
  Widget build(BuildContext context) {
    if (values.isEmpty) {
      return SizedBox(
        height: height,
        child: Center(
          child: Text('기록 없음', style: TextStyle(fontSize: 12, color: style.mutedOr)),
        ),
      );
    }
    return Semantics(
      label: semanticLabel,
      child: SizedBox(
        height: height,
        width: double.infinity,
        child: CustomPaint(
          painter: _MiniBarPainter(
            values: values,
            labels: labels,
            showValues: showValues,
            maxValue: maxValue,
            highlightIndex: highlightIndex,
            bar: style.foreground,
            muted: style.mutedOr,
          ),
        ),
      ),
    );
  }
}

class _MiniBarPainter extends CustomPainter {
  final List<num> values;
  final List<String>? labels;
  final bool showValues;
  final num? maxValue;
  final int? highlightIndex;
  final Color bar;
  final Color muted;

  const _MiniBarPainter({
    required this.values,
    required this.labels,
    required this.showValues,
    required this.maxValue,
    required this.highlightIndex,
    required this.bar,
    required this.muted,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final peak = (maxValue ?? values.reduce((a, b) => a > b ? a : b)).toDouble();
    if (peak <= 0) return;

    final labelH = labels == null ? 0.0 : 16.0;
    final valueH = showValues ? 14.0 : 0.0;
    final plotH = max(1.0, size.height - labelH - valueH);
    final slot = size.width / values.length;
    final barW = min(28.0, slot * 0.6);

    for (var i = 0; i < values.length; i++) {
      final cx = slot * i + slot / 2;
      final frac = (values[i].toDouble() / peak).clamp(0.0, 1.0);
      final h = max(3.0, plotH * frac);
      final top = valueH + (plotH - h);
      final dim = highlightIndex != null && highlightIndex != i;
      final rect = RRect.fromRectAndRadius(
        Rect.fromLTWH(cx - barW / 2, top, barW, h),
        const Radius.circular(6),
      );
      // 비강조 막대: 예전엔 bar를 알파 0.35로 깔았는데, 새 팔레트의 밝은 색면
      // (gochujang 라임 / crimson 미드그린) 위에서 합성 결과가 2.2:1까지 떨어졌다.
      // 이미 배경별로 4.5:1 이상이 검증된 muted 토큰을 그대로 쓴다 — 알파 계산이 사라진다.
      canvas.drawRRect(rect, Paint()..color = dim ? muted : bar);

      if (showValues) {
        _text(canvas, _fmt(values[i]), Offset(cx, top - 2), muted, 11, anchorBottom: true);
      }
      final ls = labels;
      if (ls != null && i < ls.length) {
        _text(canvas, ls[i], Offset(cx, size.height - labelH + 2), muted, 11);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _MiniBarPainter old) =>
      old.values != values ||
      old.labels != labels ||
      old.highlightIndex != highlightIndex ||
      old.maxValue != maxValue ||
      old.bar != bar;
}

String _fmt(num v) => v == v.roundToDouble() ? v.round().toString() : v.toStringAsFixed(1);

/// 캔버스 텍스트 한 줄 — 중앙 정렬 기준점 [at].
void _text(Canvas canvas, String s, Offset at, Color color, double size,
    {bool anchorBottom = false, FontWeight weight = FontWeight.w600}) {
  final tp = TextPainter(
    text: TextSpan(
      text: s,
      style: TextStyle(
        color: color,
        fontSize: size,
        fontWeight: weight,
        fontFamily: 'Pretendard',
        fontFeatures: const [FontFeature.tabularFigures()],
      ),
    ),
    textDirection: TextDirection.ltr,
    maxLines: 1,
  )..layout();
  final dy = anchorBottom ? at.dy - tp.height : at.dy;
  tp.paint(canvas, Offset(at.dx - tp.width / 2, dy));
}

/// 두 시리즈를 세트별로 나란히 비교(오늘 vs 이전). `/compare`의 today.sets[]/previous.sets[]용.
/// 색만으로 구분하지 않는다 — 이전 시리즈는 **윤곽선 막대**로 그려 형태로도 구분된다(WCAG 1.4.1).
class PairedBarChart extends StatelessWidget {
  final List<num> current;
  final List<num> previous;
  final BlockStyle style;
  final String currentLabel;
  final String previousLabel;

  /// 세트 번호 등 x축 라벨. 비우면 1..n 자동.
  final List<String>? labels;
  final double height;
  final String semanticLabel;

  const PairedBarChart({
    super.key,
    required this.current,
    required this.previous,
    required this.style,
    required this.semanticLabel,
    this.currentLabel = '오늘',
    this.previousLabel = '이전',
    this.labels,
    this.height = 110,
  });

  @override
  Widget build(BuildContext context) {
    final n = max(current.length, previous.length);
    if (n == 0) {
      return SizedBox(
        height: height,
        child: Center(
          child: Text('비교할 기록 없음', style: TextStyle(fontSize: 12, color: style.mutedOr)),
        ),
      );
    }
    final xs = labels ?? [for (var i = 1; i <= n; i++) '$i'];
    return Semantics(
      label: semanticLabel,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: height,
            width: double.infinity,
            child: CustomPaint(
              painter: _PairedBarPainter(
                current: current,
                previous: previous,
                labels: xs,
                bar: style.foreground,
                muted: style.mutedOr,
              ),
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              _legendSwatch(filled: true, color: style.foreground),
              const SizedBox(width: 6),
              Text(currentLabel, style: TextStyle(fontSize: 11, color: style.mutedOr)),
              const SizedBox(width: 14),
              _legendSwatch(filled: false, color: style.foreground),
              const SizedBox(width: 6),
              Text(previousLabel, style: TextStyle(fontSize: 11, color: style.mutedOr)),
            ],
          ),
        ],
      ),
    );
  }

  static Widget _legendSwatch({required bool filled, required Color color}) => Container(
        width: 12,
        height: 12,
        decoration: BoxDecoration(
          color: filled ? color : Colors.transparent,
          border: filled ? null : Border.all(color: color, width: 1.5),
          borderRadius: BorderRadius.circular(3),
        ),
      );
}

class _PairedBarPainter extends CustomPainter {
  final List<num> current;
  final List<num> previous;
  final List<String> labels;
  final Color bar;
  final Color muted;

  const _PairedBarPainter({
    required this.current,
    required this.previous,
    required this.labels,
    required this.bar,
    required this.muted,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final n = max(current.length, previous.length);
    if (n == 0) return;
    final all = [...current, ...previous].map((v) => v.toDouble());
    final peak = all.fold<double>(0, max);
    if (peak <= 0) return;

    const labelH = 16.0;
    final plotH = max(1.0, size.height - labelH);
    final slot = size.width / n;
    final barW = min(14.0, slot * 0.3);
    final gap = barW * 0.35;

    final fill = Paint()..color = bar;
    final stroke = Paint()
      ..color = bar.withValues(alpha: 0.75)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    for (var i = 0; i < n; i++) {
      final cx = slot * i + slot / 2;

      void drawBar(double? v, double dx, Paint paint, bool outlined) {
        if (v == null) return;
        final h = max(3.0, plotH * (v / peak).clamp(0.0, 1.0));
        final inset = outlined ? 0.75 : 0.0;
        final rect = RRect.fromRectAndRadius(
          Rect.fromLTWH(cx + dx - barW / 2 + inset, plotH - h + inset, barW - inset * 2,
              max(1.0, h - inset * 2)),
          const Radius.circular(4),
        );
        canvas.drawRRect(rect, paint);
      }

      drawBar(i < previous.length ? previous[i].toDouble() : null, -(barW + gap) / 2, stroke, true);
      drawBar(i < current.length ? current[i].toDouble() : null, (barW + gap) / 2, fill, false);

      if (i < labels.length) {
        _text(canvas, labels[i], Offset(cx, plotH + 2), muted, 11);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _PairedBarPainter old) =>
      old.current != current || old.previous != previous || old.bar != bar;
}

/// 연속 운동일 배지. 아이콘 + 숫자 + 라벨 — 숫자만으로도 의미가 서게 라벨을 항상 붙인다.
class StreakBadge extends StatelessWidget {
  final int days;
  final BlockStyle style;
  final String label;
  final IconData icon;

  const StreakBadge({
    super.key,
    required this.days,
    required this.style,
    this.label = '연속',
    this.icon = Icons.local_fire_department_rounded,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '$label $days일',
      container: true,
      excludeSemantics: true,
      child: Container(
        constraints: const BoxConstraints(minHeight: 36),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        decoration: BoxDecoration(
          color: style.background,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: style.foreground),
            const SizedBox(width: 6),
            Text('$days',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                  color: style.foreground,
                  fontFeatures: const [FontFeature.tabularFigures()],
                )),
            const SizedBox(width: 3),
            Text('일 $label',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: style.mutedOr)),
          ],
        ),
      ),
    );
  }
}

/// 폼 점수 게이지 — 링 채움으로 점수를 표현 (dataviz: meter는 채움색이 심각도를 담당).
/// 값·구간 색 변경 시 300ms easeOut으로 트윈 (reduced-motion 시 즉시 반영).
/// [color]는 보통 [formScoreColor]로 뽑는다. [trackColor] 생략 시 테마의 surfaceContainerHighest.
class FormScoreRing extends StatelessWidget {
  final int? score;
  final Color color;
  final Color? trackColor;
  final double size;
  final double strokeWidth;

  /// 지정 시 채움 호를 이 그라데이션으로 그린다. 현재 화면에선 미사용 — 링은 [color]=
  /// [formScoreColor](의미색) 솔리드로 그린다(호 vs 트랙 4.27~5.34:1로 1.4.11 3:1 통과).
  /// 산호↔청록 브랜드 그라데이션은 걷어냈고 훅만 남겨둔다.
  final Gradient? gradient;

  const FormScoreRing({
    super.key,
    required this.score,
    required this.color,
    this.trackColor,
    this.size = 72,
    this.strokeWidth = 8,
    this.gradient,
  });

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final duration = reduceMotion ? Duration.zero : const Duration(milliseconds: 300);
    final track = trackColor ?? Theme.of(context).colorScheme.surfaceContainerHighest;
    final fraction = (score ?? 0) / 100;
    return Semantics(
      label: score != null ? '폼 점수 $score점' : '폼 점수 없음',
      child: SizedBox(
        width: size,
        height: size,
        child: TweenAnimationBuilder<Color?>(
          tween: ColorTween(begin: color, end: color),
          duration: duration,
          builder: (context, animatedColor, _) {
            final c = animatedColor ?? color;
            return TweenAnimationBuilder<double>(
              tween: Tween<double>(begin: fraction, end: fraction),
              duration: duration,
              curve: Curves.easeOut,
              builder: (context, value, __) {
                return CustomPaint(
                  painter: _RingPainter(
                    fraction: value,
                    color: c,
                    track: track,
                    strokeWidth: strokeWidth,
                    gradient: gradient,
                  ),
                  child: Center(
                    child: Text(
                      score != null ? '$score' : '-',
                      style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: size * 0.28,
                          color: c,
                          fontFeatures: const [FontFeature.tabularFigures()]),
                    ),
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  final double fraction;
  final Color color;
  final Color track;
  final double strokeWidth;
  final Gradient? gradient;
  const _RingPainter({
    required this.fraction,
    required this.color,
    required this.track,
    required this.strokeWidth,
    this.gradient,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = (size.shortestSide - strokeWidth) / 2;
    final trackPaint = Paint()
      ..color = track
      ..strokeWidth = strokeWidth
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    canvas.drawCircle(center, radius, trackPaint);
    if (fraction <= 0) return;
    final rect = Rect.fromCircle(center: center, radius: radius);
    final fill = Paint()
      ..strokeWidth = strokeWidth
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    if (gradient != null) {
      fill.shader = gradient!.createShader(rect);
    } else {
      fill.color = color;
    }
    canvas.drawArc(
      rect,
      -pi / 2,
      2 * pi * fraction.clamp(0, 1),
      false,
      fill,
    );
  }

  @override
  bool shouldRepaint(covariant _RingPainter oldDelegate) =>
      oldDelegate.fraction != fraction ||
      oldDelegate.color != color ||
      oldDelegate.track != track ||
      oldDelegate.gradient != gradient;
}

/// The Fit 브랜드 로고 마크.
/// `assets/logo/logo_a.png`·`logo_b.png` 두 이미지를 크로스페이드 + 미세 회전(±2.9°)으로
/// 번갈아 보여준다. disableAnimations면 정지 이미지 1장(logo_a).
///
/// **자산이 아직 없을 수 있다** — `Image.asset`의 errorBuilder로 코랄 원형 + 이니셜 'TF'
/// 폴백을 그려 크래시를 막는다. 자산이 없으면 두 슬롯 모두 폴백이 되어 사실상 정지 로고가 된다.
class AppLogo extends StatefulWidget {
  final double size;

  /// false면 크로스페이드/회전 애니메이션 없이 정지 로고(logo_a) 한 장만 보여준다.
  /// 로그인처럼 "애니메이션 없이" 로고만 필요한 화면에서 쓴다. 기본 true.
  final bool animate;

  const AppLogo({super.key, this.size = 72, this.animate = true});

  @override
  State<AppLogo> createState() => _AppLogoState();
}

class _AppLogoState extends State<AppLogo> with SingleTickerProviderStateMixin {
  late final AnimationController _controller =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 2600));
  bool _animate = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // widget.animate가 false면(로그인 등) 접근성 설정과 무관하게 항상 정지.
    _animate = widget.animate && !MediaQuery.of(context).disableAnimations;
    if (_animate) {
      if (!_controller.isAnimating) _controller.repeat(reverse: true);
    } else {
      _controller.stop();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Widget _image(String asset) => Image.asset(
        asset,
        width: widget.size,
        height: widget.size,
        fit: BoxFit.contain,
        gaplessPlayback: true,
        errorBuilder: (_, __, ___) => _fallback(),
      );

  Widget _fallback() => Container(
        width: widget.size,
        height: widget.size,
        alignment: Alignment.center,
        decoration: const BoxDecoration(color: AppColors.primary, shape: BoxShape.circle),
        child: Text(
          'TF',
          style: TextStyle(
            color: AppColors.onPrimary,
            fontWeight: FontWeight.w800,
            fontSize: widget.size * 0.34,
            letterSpacing: 0.5,
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'The Fit',
      image: true,
      child: SizedBox(
        width: widget.size,
        height: widget.size,
        child: _animate
            ? AnimatedBuilder(
                animation: _controller,
                builder: (context, _) {
                  final t = Curves.easeInOut.transform(_controller.value);
                  final angle = (t - 0.5) * 0.10; // ±0.05rad ≈ ±2.9°
                  return Stack(
                    alignment: Alignment.center,
                    children: [
                      Opacity(
                        opacity: 1 - t,
                        child: Transform.rotate(angle: angle, child: _image('assets/logo/logo_a.png')),
                      ),
                      Opacity(
                        opacity: t,
                        child: Transform.rotate(angle: angle, child: _image('assets/logo/logo_b.png')),
                      ),
                    ],
                  );
                },
              )
            : _image('assets/logo/logo_a.png'),
      ),
    );
  }
}
