import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'api.dart';
import 'screens/login.dart';
import 'screens/root.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // 웹에서 시맨틱 트리를 처음부터 켠다. 이게 없으면 캔버스에만 그려져서
  // 스크린리더도, 자동 캡처(UI/UX 갤러리)도 버튼을 찾지 못한다.
  SemanticsBinding.instance.ensureSemantics();
  runApp(const HohowattApp());
}

// ---------------------------------------------------------------------------
// 팔레트: The Fit — iOS 시안 기반 "플랫 iOS". (크리스탈 글라스에서 전환)
// 시안(iOS 앱 디자인 리뉴얼/The Fit iOS.dc.html)은 블러·그라데이션 백드롭이 없다:
//   * 배경(60): 단색 오프화이트 scaffold #F3F2F2. 그라데이션 백드롭 없음.
//   * 표면(30): 플랫 흰 카드([GlassCard] = #FFF + 얇은 보더 + 미세 그림자) 또는 [AppBlocks] 색면.
//   * 액센트(10): 솔리드 코랄([AppColors.primary] #F26B4E 채움, [primaryText] #C63D22 텍스트/링크).
//
// UI 액센트는 코랄 단색만 — 시안 UI엔 청록이 없다(청록은 로고 마크 전용). 폼점수 3색만 예외로
// 색 구분이 필요해 틸/앰버/레드를 유지한다([formScoreColor]).
//
// [AppColors]와 [AppDark]의 2단 구조는 유지:
//   * AppColors = 일반 화면(home/calendar/summary/profile/guide/login/onboarding)의
//     "라이트" 세트. 카드면 = 흰색 #FFFFFF, 배경 = 오프화이트 #F3F2F2.
//   * AppDark   = 몰입 화면(workout)의 "트루 블랙" 세트. 카메라 프리뷰가 화면을 채우므로
//     scaffold #000000 유지. 액센트는 코랄/틸 '브라이트'(검정 위 8~13:1).
//
// **대비 규칙(검증됨): 밝은 코랄 채움(#F26B4E) 위 텍스트/아이콘은 어두운 잉크(#26120B, 5.95:1).**
//   흰 텍스트는 밝은 코랄 위에서 FAIL — 시안이 다크 텍스트를 쓰는 이유다.
// common.dart의 `dark:` 플래그 12개가 라이트/다크 분기를 구동한다. 값만 갈아끼웠다.
// ---------------------------------------------------------------------------

/// 액센트 채움 그라데이션 훅. 시안은 솔리드 코랄만 쓴다 — [coral]은 단일 hue 2스톱(사실상 솔리드).
/// **채움(FILL) 위 텍스트/아이콘은 어두운 잉크([AppColors.onPrimary] #26120B) — coral 위 5.95:1 AA.**
/// [backdrop]/[backdropDark]는 구 글라스 백드롭 잔재 — 플랫 전환 후 [GradientBackground]는
/// 이들을 쓰지 않고 단색 scaffold를 칠한다. 심볼은 호환을 위해 남긴다(화면이 참조할 수 있음).
class AppGradients {
  AppGradients._();

  /// 솔리드 코랄 채움. GradientButton·아바타 등 "코랄 면" 액센트용.
  /// DecoratedBox는 gradient 타입을 받으므로 단일 hue(coral_mid) 2스톱으로 채운다.
  /// 위 텍스트/아이콘은 다크 잉크: coral #F26B4E 위 #26120B 5.95:1 AA.
  static const coral = LinearGradient(
    colors: [Color(0xFFF26B4E), Color(0xFFF26B4E)], // coral_mid 솔리드
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  /// (레거시) 구 글라스 백드롭. 플랫 전환 후 미사용 — [GradientBackground]가 단색 scaffold를 칠한다.
  static const backdrop = LinearGradient(
    colors: [Color(0xFFFFF4F0), Color(0xFFF7FAF9), Color(0xFFEDF6F3)],
    stops: [0.0, 0.5, 1.0],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  /// (레거시) 구 workout 백드롭. 플랫 전환 후 미사용 — 단색 트루블랙을 칠한다.
  static const backdropDark = LinearGradient(
    colors: [Color(0xFF0A0C0D), Color(0xFF000000)],
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
  );
}

/// 일반 화면 "플랫 라이트" 세트. 대비 기준 표면 = 흰 카드 #FFFFFF / 오프화이트 배경 #F3F2F2.
class AppColors {
  AppColors._();
  static const primary = Color(0xFFF26B4E); // coral_mid — 시안 채움 액센트(버튼 bg·아바타·히트맵 최대).
  // **채움(FILL) 전용**: 위 텍스트/아이콘은 다크 잉크([onPrimary] #26120B, 5.95:1 AA).
  // **작은 텍스트 색으로 쓰지 마라** — 흰 위 3.00으로 큰 텍스트(3:1)만 통과, 본문은 [primaryText].
  static const onPrimary = Color(0xFF26120B); // 코랄 채움 위 다크 텍스트/아이콘 — #F26B4E 위 5.95:1 AA.
  static const primaryText = Color(0xFFC63D22); // 텍스트/보더 안전 산호 — 흰 5.13 / 오프화이트 4.59:1 AA.
  // primary를 '작은 텍스트·보더 색'으로 쓰던 자리는 이 토큰으로 교체한다(작은 링크·강조·아웃라인 버튼).
  static const secondary = Color(0xFFB45309); // 앰버 — 폼점수 mid + Scheme.secondary. 흰 위 5.02:1
  static const success = Color(0xFF0F766E); // Teal-green(good, 폼점수 전용) — 흰 위 5.47:1
  static const error = Color(0xFFBE123C); // Crimson red(bad) — 산호와 구분되는 붉은 톤. 흰 위 6.29:1
  static const scaffold = Color(0xFFF3F2F2); // 오프화이트 단색 배경(시안 --color-bg). 그라데이션 없음.
  static const surface = Color(0xFFFFFFFF); // 플랫 흰 카드면
  static const surfaceMuted = Color(0xFFE7EEEC); // 입력 fill/스켈레톤/스낵바/세그먼트 트랙(시안 세그먼트 bg)
  static const border = Color(0xFFEBE9E9); // 카드 헤어라인 — 시안 rgba(28,43,46,.07) 근사(장식용)
  static const foreground = Color(0xFF1C2B2E); // ink — 흰 위 14.64 / 오프화이트 위 13.10:1 AAA
  static const foregroundMuted = Color(0xFF5C6A6C); // 시안 muted/캡션 — 흰 위 5.63 / 오프화이트 위 5.03:1 AA
}

/// 몰입 화면(workout) 트루 블랙 세트. 대비 기준 배경은 scaffold #000000.
/// 카메라 프리뷰 위 오버레이가 살아야 하므로 트루블랙 유지 — 여기만 다크.
/// 액센트는 산호/청록 '브라이트': 어두운 코랄은 검정 위 대비가 안 나와 밝은 톤을 쓴다.
class AppDark {
  AppDark._();
  static const primary = Color(0xFFFF8A6B); // coral_bright — 검정 위 9.10:1 AAA
  static const onPrimary = Color(0xFF2A1008); // 브라이트 코랄 위 텍스트 — 7.74:1 AAA
  static const primaryText = primary; // 다크에선 coral_bright가 검정 위 9.1:1 → 텍스트로도 안전
  static const secondary = Color(0xFFFBBF24); // 앰버 — 폼점수 mid, 검정 위 12.58:1 AAA
  static const success = Color(0xFF5EE0CE); // teal_bright(good) — 검정 위 13.03:1 AAA
  static const error = Color(0xFFF87171); // Red(bad) — 검정 위 7.59:1 AAA
  static const dangerFill = Color(0xFFB22C2C); // 중단 버튼 채움 — 흰 텍스트 6.38:1,
  // 검정 대비 3.29:1로 1.4.11(3:1) 충족. 원색 레드는 검정 위 2.1:1이라 버튼 면이 사라진다.
  static const scaffold = Color(0xFF000000); // 트루 블랙 — 카메라 프리뷰 뒤
  static const surface = Color(0xFF1F2123); // 다크 글라스 베이스 / 살짝 띄운 중립 다크
  static const surfaceMuted = Color(0xFF2E3133); // 링 트랙/입력
  static const border = Color(0xFF3A3D3F); // 장식용 경계(검정 위 저대비 — 아래 참조)
  static const foreground = Color(0xFFFFFFFF); // 검정 위 21:1 AAA
  static const foregroundMuted = Color(0xFFA0A6A6); // 검정 위 8.0:1 AAA
  // border/surface는 트루 블랙 위 대비가 낮다(장식). workout 카드는 대개 카메라 위에 스크림으로
  // 분리되고, 정보 요소(링·버튼·점수)는 accent(검정 위 9:1+)로 전달된다. surfaceMuted는
  // FormScoreRing 트랙이지만 1.4.11의 "이해에 필요한 그래픽 객체"가 아니다 — 점수는 링 중앙
  // 숫자로, 크기는 채움 호(scoreColor)로 이미 전달된다. 의도된 예외다.
}

/// 색면 카드 한 벌 — 카드 배경 + 그 위 전경 + 그 위 보조 톤.
/// 셋이 항상 짝으로 다니므로 묶어서 넘긴다(사용처에서 배경만 바꾸고 전경을 잊는 사고 방지).
@immutable
class BlockStyle {
  /// 카드 면 전체를 채우는 색.
  final Color background;

  /// 그 위 본문/제목 색. background 대비 4.5:1 이상 검증됨.
  final Color foreground;

  /// 그 위 보조(캡션) 색. null이면 이 색면 위에서 4.5:1을 만족하는 보조 톤이 없다는 뜻 →
  /// 단일 톤(foreground)만 써라. [mutedOr]가 자동으로 foreground로 떨어뜨린다.
  final Color? muted;

  const BlockStyle({required this.background, required this.foreground, this.muted});

  Color get mutedOr => muted ?? foreground;
}

/// 60-30-10 운영의 "30" — 색면 카드 토큰.
/// 60(배경): scaffold는 라이트/트루블랙 단색. **여기 있는 색을 scaffold에 쓰지 마라.**
/// 30(색면): 카드 단위로 배경색을 통째로 바꾼다 — 중립 라이트부터 코랄 솔리드까지.
/// 10(액센트): [AppColors.primary] (Coral) — 큰 숫자·CTA·기록일.
///
/// **슬롯 이름은 구 팔레트(네이비/크림슨/고추장/크림)에서 그대로 물려받았다.**
/// 화면 6개가 이 이름을 참조하므로 이름을 유지하고 값만 갈아끼웠다. 새 의미는 각 슬롯 주석에.
///
/// 슬롯 배치를 결정한 것은 `calendar.dart`의 히트맵이다 —
/// `cream(0) → tintGochujang(1) → crimson(2) → gochujang(3)` 순으로 농도를 읽는다.
/// 라이트 테마에선 "빈 날 = 흰색, 바쁜 날 = 진한 코랄"이 자연스러우므로 이 4개는
/// **휘도가 단조 감소하는 코랄 램프**다(1.000 > 0.750 > 0.285 > 0.162). 각 셀에 세션 개수
/// 숫자를 같이 찍으므로(WCAG 1.4.1) 램프 방향은 시각적 강도 표현일 뿐 기능 의존은 아니다.
/// 나머지 3개(navy/tintNavy/tintCrimson)는 램프 밖의 중립·틸 보조 패널이다.
class AppBlocks {
  AppBlocks._();

  // --- 솔리드 색면 (플랫 iOS 톤 — 시안 카드/스탯/히트맵 값과 정렬됨. 값 변경 없이 이미 일치.) ---

  /// 구 navy 슬롯 → **중립 글라스 패널**(옅은 청록-그레이). 코랄 램프 밖의 "쉼표" 카드.
  /// `home`의 색면 사이클, `summary`의 무난/점수없음 밴드, `calendar` 바텀시트 배경에 쓰인다.
  static const navy = BlockStyle(
    background: Color(0xFFEAF1F1), // 쿨 뉴트럴(청록 캐스트) 라이트
    foreground: Color(0xFF1C2B2E), // 13.0:1 AAA
    muted: Color(0xFF4C5F62), // 5.7:1 AA
  );

  /// 구 crimson 슬롯 → **미드 산호**(히트맵 lv2). 코랄 솔리드 바로 아래 단계.
  /// 밝은 산호라 전경이 어둡다 — 위 텍스트는 반드시 이 foreground(ink 계열)를 쓴다.
  static const crimson = BlockStyle(
    background: Color(0xFFF7A98E), // 미드 산호
    foreground: Color(0xFF2A140C), // 9.15:1 AAA
    muted: Color(0xFF3E2015), // 7.75:1 AAA
  );

  /// 구 gochujang 슬롯 → **산호 솔리드**(히트맵 lv3 = 최다). 팔레트의 10 = 브랜드 산호(coral_mid).
  /// 밝은 산호라 흰 텍스트 대신 **어두운 잉크**를 얹는다(흰색은 coral_mid 위 2.84 FAIL).
  static const gochujang = BlockStyle(
    background: Color(0xFFF26B4E), // coral_mid
    foreground: Color(0xFF1C2B2E), // ink — 4.87:1 AA
    // muted 없음: 이 밝은 산호 위에서 ink보다 덜 튀며 4.5:1을 넘는 보조 톤은 불가 → mutedOr가 ink로 폴백.
  );

  /// 구 cream 슬롯 → **기본 흰 카드면**(히트맵 lv0 = 기록 없음).
  /// 값이 [AppColors.surface]와 같다 — 일반 카드와 색면 카드가 같은 면을 공유한다.
  /// 백드롭 대비가 낮으므로 사용처에서 `outlined: true`가 여전히 필요하다.
  static const cream = BlockStyle(
    background: AppColors.surface, // #FFFFFF
    foreground: Color(0xFF1C2B2E), // 13.8:1 AAA
    muted: Color(0xFF5C6A6C), // 5.6:1 AA
  );

  // --- 소프트 틴트 색면 ---

  /// 구 tintNavy 슬롯 → **가장 옅은 중립 틴트**. `profile`의 outlined 카드용.
  static const tintNavy = BlockStyle(
    background: Color(0xFFEEF3F3),
    foreground: Color(0xFF1C2B2E), // 13.5:1 AAA
    muted: Color(0xFF4C5F62), // 6.0:1 AA
  );

  /// 구 tintCrimson 슬롯 → **페일 청록 틴트**(보조 액센트). `profile`의 StreakBadge·outlined 카드용.
  /// [tintGochujang](산호 틴트)과 색상(hue)이 갈린다 — 이쪽은 청록. 전경은 딥 청록-잉크.
  static const tintCrimson = BlockStyle(
    background: Color(0xFFD6EEEA), // 페일 청록
    foreground: Color(0xFF0B3B36), // 10.2:1 AAA (딥 청록) — outlined 합성 3.2:1(≥3) 위해 충분히 깊게
    muted: Color(0xFF2F615B), // 5.79:1 AA
  );

  /// 구 tintGochujang 슬롯 → **페일 산호 틴트**(히트맵 lv1).
  static const tintGochujang = BlockStyle(
    background: Color(0xFFFFE2D8), // 페일 산호
    foreground: Color(0xFF1C2B2E), // 12.3:1 AAA
    muted: Color(0xFF8A3A22), // 6.3:1 AA
  );

  /// workout(트루 블랙) 화면에서 "중립 카드" 자리. 구조 그대로 — 값만 새 다크 토큰을 따른다.
  static const darkNeutral = BlockStyle(
    background: AppDark.surface,
    foreground: AppDark.foreground,
    muted: AppDark.foregroundMuted,
  );
}

/// 화면 전환 공통 모션 — 150~250ms 페이드+슬라이드, prefers-reduced-motion 존중.
/// (ui-ux-pro-max: micro-interaction 150-300ms 가이드라인 적용)
Route<T> fadeRoute<T>(BuildContext context, WidgetBuilder builder) {
  final reduceMotion = MediaQuery.of(context).disableAnimations;
  return PageRouteBuilder<T>(
    pageBuilder: (context, animation, secondaryAnimation) => builder(context),
    transitionDuration: reduceMotion ? Duration.zero : const Duration(milliseconds: 220),
    reverseTransitionDuration: reduceMotion ? Duration.zero : const Duration(milliseconds: 180),
    transitionsBuilder: (context, animation, secondaryAnimation, child) {
      if (reduceMotion) return child;
      final curved = CurvedAnimation(parent: animation, curve: Curves.easeOut);
      return FadeTransition(
        opacity: curved,
        child: SlideTransition(
          position: Tween<Offset>(begin: const Offset(0, 0.03), end: Offset.zero).animate(curved),
          child: child,
        ),
      );
    },
  );
}

/// 딥다크(일반)/트루블랙(workout) 두 세트를 하나의 정의에서 만든다.
/// dark: true는 몰입 화면(workout) 전용 — 화면 단위로 Theme 위젯에 주입한다.
/// 두 세트 모두 Brightness.dark다. 라이트 테마는 더 이상 없다.
ThemeData buildAppTheme({required bool dark}) {
  final primary = dark ? AppDark.primary : AppColors.primary;
  final onPrimary = dark ? AppDark.onPrimary : AppColors.onPrimary;
  final secondary = dark ? AppDark.secondary : AppColors.secondary;
  final success = dark ? AppDark.success : AppColors.success;
  final error = dark ? AppDark.error : AppColors.error;
  final scaffold = dark ? AppDark.scaffold : AppColors.scaffold;
  final surface = dark ? AppDark.surface : AppColors.surface;
  final surfaceMuted = dark ? AppDark.surfaceMuted : AppColors.surfaceMuted;
  final border = dark ? AppDark.border : AppColors.border;
  final foreground = dark ? AppDark.foreground : AppColors.foreground;
  final foregroundMuted = dark ? AppDark.foregroundMuted : AppColors.foregroundMuted;
  // 액센트 위 전경 색. primary(코랄)와 나머지 액센트(앰버/틸/레드)는 밝기가 갈리므로 분리한다:
  //   * 라이트: primary=밝은 코랄 → onPrimary=다크(#26120B). 그러나 secondary/tertiary/error는
  //     어두운 색이라 그 위엔 **흰 텍스트**가 산다(앰버 5.02 / 틸 5.47 / 레드 6.29:1). → onAccent=흰색.
  //   * 다크(workout): 액센트가 전부 브라이트라 어두운 텍스트(onPrimary #2A1008)가 산다 → onAccent=onPrimary.
  final onAccent = dark ? onPrimary : const Color(0xFFFFFFFF);

  // 텍스트 링크/버튼용 산호 = [AppColors.primaryText]/[AppDark.primaryText].
  // primary(coral_deep)는 흰 위 4.21이라 작은 텍스트 링크엔 미달 → 텍스트 전용 토큰을 쓴다.
  final link = dark ? AppDark.primaryText : AppColors.primaryText;

  // 입력 필드 라벨/힌트는 fill(surfaceMuted) 위에 앉는다. 라이트 fill #E7EEEC 위에서
  // foregroundMuted(#45585B)가 이미 5:1↑로 통과하므로 그대로 쓴다.
  // 다크 fill #2E3133 위에선 foregroundMuted #A0A6A6가 이미 통과.
  final inputMuted = foregroundMuted;

  final brightness = dark ? Brightness.dark : Brightness.light;

  final colorScheme = ColorScheme(
    brightness: brightness,
    primary: primary,
    onPrimary: onPrimary,
    secondary: secondary,
    onSecondary: onAccent,
    tertiary: success,
    onTertiary: onAccent,
    error: error,
    onError: onAccent,
    surface: surface,
    onSurface: foreground,
    surfaceContainerHighest: surfaceMuted,
    outline: border,
  );

  // 타이포 위계 — Pretendard(한글 지원) 유지. fontFamily는 ThemeData에서 전역 지정.
  final textTheme = const TextTheme(
    headlineSmall: TextStyle(fontWeight: FontWeight.w700, height: 1.15),
    titleLarge: TextStyle(fontWeight: FontWeight.w700),
    titleMedium: TextStyle(fontWeight: FontWeight.w700, letterSpacing: -0.1),
    displayMedium: TextStyle(fontWeight: FontWeight.w800, letterSpacing: 0),
    bodyLarge: TextStyle(height: 1.4),
    bodyMedium: TextStyle(height: 1.4),
    labelLarge: TextStyle(fontWeight: FontWeight.w700, letterSpacing: 0.2),
  ).apply(bodyColor: foreground, displayColor: foreground);

  // iOS는 그림자보다 '면 분리'로 위계를 만든다 — 라이트는 아주 미세한 그림자(시안 0.04),
  // 다크(workout)는 순검정 낮은 그림자. 카드 정의는 흰 면 vs 오프화이트 scaffold + 헤어라인 보더가 담당.
  final shadow = dark
      ? Colors.black.withValues(alpha: 0.5)
      : Colors.black.withValues(alpha: 0.04);

  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: colorScheme,
    scaffoldBackgroundColor: scaffold,
    fontFamily: 'Pretendard',
    textTheme: textTheme,
    iconTheme: IconThemeData(color: foreground),
    appBarTheme: AppBarTheme(
      backgroundColor: scaffold,
      foregroundColor: foreground,
      surfaceTintColor: Colors.transparent,
      centerTitle: false,
      elevation: 0,
      titleTextStyle: TextStyle(
        fontFamily: 'Pretendard',
        fontWeight: FontWeight.w700,
        fontSize: 22,
        color: foreground,
      ),
    ),
    cardTheme: CardThemeData(
      color: surface,
      elevation: 0, // 다크에선 그림자로 면이 안 뜬다 → 보더로 세운다
      shadowColor: shadow,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16), // 시안 흰 카드 라운드(로그인/온보딩 16)
        side: BorderSide(color: border, width: 1),
      ),
      margin: EdgeInsets.zero,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: surface,
      // 인디케이터 알약(primary 틴트) 위에 선택 아이콘/라벨(link=더 깊은 산호)이 얹힌다.
      // 선택 색을 link로 쓰는 이유: 밝아진 coral_deep은 12px 라벨로 흰 위 4.21(<4.5)이라
      // 텍스트가 미달 → 텍스트 안전 산호 link(흰 위 5.13, 다크는 coral_bright 7.0)로 올린다.
      //   * 라이트: primary@0.20 페일 산호 알약. 그 위 link 아이콘 3.92:1(≥3, 1.4.11).
      //   * 다크(workout): coral_bright@0.25 알약. 그 위 coral_bright 아이콘 4.37:1.
      indicatorColor: primary.withValues(alpha: dark ? 0.25 : 0.20),
      surfaceTintColor: Colors.transparent,
      elevation: 1,
      shadowColor: shadow,
      labelTextStyle: WidgetStateProperty.resolveWith((states) => TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: states.contains(WidgetState.selected) ? link : foregroundMuted,
          )),
      iconTheme: WidgetStateProperty.resolveWith((states) => IconThemeData(
            color: states.contains(WidgetState.selected) ? link : foregroundMuted,
          )),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: primary,
        foregroundColor: onPrimary,
        minimumSize: const Size.fromHeight(52),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
        // 시안 CTA는 필(pill) — height 52, border-radius 26. StadiumBorder로 항상 알약.
        shape: const StadiumBorder(),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: foreground,
        // 경계는 장식이 아니라 조작 가능 영역 표시 → 배경 대비 3:1 이상 필요.
        //   * 라이트: 텍스트 안전 산호 link(#C63D22) — 흰 5.13 / 오프화이트 4.59:1. (밝은 coral_mid는
        //     오프화이트 위 2.69로 FAIL이라 보더에 못 쓴다 → 더 진한 link를 쓴다.)
        //   * 다크(workout): 브라이트 코랄@0.7 → 검정 위 6:1+.
        side: BorderSide(
          color: dark ? primary.withValues(alpha: 0.7) : link,
          width: 1.5,
        ),
        minimumSize: const Size.fromHeight(52),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
        shape: const StadiumBorder(),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: link, // 라이트=darken 코랄(scaffold 4.99) / 다크=브라이트 코랄
        minimumSize: const Size(48, 48), // 접근성 최소 터치 타깃
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: surfaceMuted,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide.none,
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide.none,
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: primary, width: 2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: error, width: 1.5),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: error, width: 2),
      ),
      labelStyle: TextStyle(color: inputMuted),
      hintStyle: TextStyle(color: inputMuted),
      errorStyle: TextStyle(color: error, fontWeight: FontWeight.w600),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      color: primary,
      linearTrackColor: surfaceMuted,
      circularTrackColor: surfaceMuted,
    ),
    dividerTheme: DividerThemeData(color: border, space: 1),
    dropdownMenuTheme: DropdownMenuThemeData(
      textStyle: TextStyle(color: foreground),
      menuStyle: MenuStyle(backgroundColor: WidgetStateProperty.all(surface)),
    ),
    snackBarTheme: SnackBarThemeData(
      // 전면 다크가 되면서 "배경 반전"이 성립하지 않는다(반전하면 흰 판이 떠서 눈을 때린다).
      // 대신 surfaceMuted로 한 계단 띄워 scaffold·카드 어느 쪽 위에서도 분리되게 한다.
      backgroundColor: surfaceMuted,
      contentTextStyle: TextStyle(
        fontFamily: 'Pretendard',
        color: foreground, // surfaceMuted 위 11.95:1 AAA
      ),
      actionTextColor: link, // 라이트 surfaceMuted 위 4.60:1 (primary는 4.10으로 미달) / 다크 8.7:1
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: surface,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: TextStyle(
        fontFamily: 'Pretendard',
        fontWeight: FontWeight.w700,
        fontSize: 18,
        color: foreground,
      ),
      contentTextStyle: TextStyle(fontFamily: 'Pretendard', color: foreground, height: 1.4),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    ),
  );
}

class HohowattApp extends StatelessWidget {
  const HohowattApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'The Fit',
      theme: buildAppTheme(dark: false),
      home: Api.instance.isLoggedIn ? const RootScreen() : const LoginScreen(),
    );
  }
}
