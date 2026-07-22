import 'dart:math';

import 'package:flutter/material.dart';
import '../main.dart';

/// 폼 점수 구간 색상 규칙 — 80↑ success(라임), 60↑ secondary(앰버), 미만 error(소프트 레드).
/// dark: true는 트루 블랙 몰입 화면(workout)용. 새 팔레트에선 두 세트의 구간색 값이 같지만
/// 시그니처는 유지한다 — 호출부 6개가 쓰고 있고, 세트가 다시 갈라질 때 여기만 고치면 된다.
/// 세 색 모두 검증됨: 딥다크 12.85/11.60/7.00:1, 검정 13.93/12.58/7.59:1,
/// cream 색면 11.66/10.53/6.36:1, navy 색면 9.22/8.33/5.03:1 — 전부 4.5:1 이상.
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
      // 카드면 위에 전경색을 합성한 결과가 **scaffold** 대비 3:1을 넘어야 한다(1.4.11).
      // 새 다크 팔레트에서 0.55 합성 결과: cream 6.14 / tintNavy 6.47 / tint그린 7.72 /
      // navy 6.86 / crimson 9.02 / gochujang 3.46 — 7개 슬롯 전부 통과.
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

  const BigStat({
    super.key,
    required this.style,
    required this.value,
    this.unit,
    this.caption,
    this.size = 56,
  });

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
                child: Text(
                  value,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: size,
                    fontWeight: FontWeight.w800,
                    height: 1.0,
                    letterSpacing: -1.5,
                    color: style.foreground,
                    fontFeatures: const [FontFeature.tabularFigures()],
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

  const FormScoreRing({
    super.key,
    required this.score,
    required this.color,
    this.trackColor,
    this.size = 72,
    this.strokeWidth = 8,
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
  const _RingPainter({
    required this.fraction,
    required this.color,
    required this.track,
    required this.strokeWidth,
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
    final fill = Paint()
      ..color = color
      ..strokeWidth = strokeWidth
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
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
      oldDelegate.track != track;
}
