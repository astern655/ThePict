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
// 팔레트: Apple Fitness 스타일 다크 + 라임 그린. 앱 전체가 다크다.
//
// [AppColors]와 [AppDark]의 관계 — 둘 다 다크다. 통합(별칭)하지 않고 2단으로 남긴 이유:
//   * AppColors = 일반 화면(home/calendar/summary/profile/guide/login/onboarding)의
//     "딥 다크" 세트. scaffold는 순검정이 아니라 #0C0E0D — 위에 얹는 카드면이 살아야 한다.
//   * AppDark   = 몰입 화면(workout)의 "트루 블랙" 세트. 카메라 프리뷰가 화면을 채우므로
//     scaffold를 #000000으로 떨어뜨려 UI가 영상 밖으로 물러나게 한다.
//   두 세트는 액센트(라임 #A3E635)를 공유하고 표면 계단만 다르다. 클래스를 합치면
//   workout의 트루 블랙 몰입감이 사라지고, common.dart의 `dark:` 플래그 12개가 전부 죽는다.
//   구조를 그대로 두고 값만 바꾼 이유이기도 하다.
// ---------------------------------------------------------------------------

/// 일반 화면 다크 세트. 대비 기준 배경은 scaffold #0C0E0D.
/// (구 이름은 "라이트/크림" 세트였다 — 이제 라이트 테마는 존재하지 않는다.)
class AppColors {
  AppColors._();
  static const primary = Color(0xFFA3E635); // Lime Accent — 딥다크 위 12.85:1 AAA
  static const onPrimary = Color(0xFF0A1400); // 딥 그린블랙 — 라임 위 12.51:1 AAA
  static const secondary = Color(0xFFFBBF24); // 앰버 — 딥다크 위 11.60:1 AAA (폼점수 60~79)
  static const success = Color(0xFFA3E635); // = primary. 액센트 하나로 통일(보고 참조)
  static const error = Color(0xFFF87171); // 소프트 레드 — 딥다크 위 7.00:1 AAA
  static const scaffold = Color(0xFF0C0E0D); // 딥 다크(거의 검정, 미세한 그린 중립)
  static const surface = Color(0xFF161A17); // 카드면 — scaffold보다 한 계단 밝게
  static const surfaceMuted = Color(0xFF2B322D); // 입력/스켈레톤/프로그레스 트랙
  static const border = Color(0xFF39423D); // 장식용 경계
  static const foreground = Color(0xFFF1F5F2); // 오프화이트 — 딥다크 위 17.60:1 AAA
  static const foregroundMuted = Color(0xFF9EA9A3); // 딥다크 위 7.99:1 AAA
}

/// 몰입 화면(workout) 트루 블랙 세트. 대비 기준 배경은 scaffold #000000.
/// 액센트·경고색은 [AppColors]와 동일 — 브랜드 그린이 화면마다 흔들리지 않게 한다.
class AppDark {
  AppDark._();
  static const primary = Color(0xFFA3E635); // Lime Accent — 검정 위 13.93:1 AAA
  static const onPrimary = Color(0xFF0A1400); // 라임 위 12.51:1 AAA
  static const secondary = Color(0xFFFBBF24); // 앰버 — 검정 위 12.58:1 AAA
  static const success = Color(0xFFA3E635); // = primary
  static const error = Color(0xFFF87171); // 검정 위 7.59:1 AAA
  static const dangerFill = Color(0xFFB22C2C); // 중단 버튼 채움 — 위 흰 텍스트 6.38:1,
  // 검정 대비 3.29:1로 1.4.11(3:1) 충족. 원색 레드는 검정 위 2.1:1이라 버튼 면이 사라진다.
  static const scaffold = Color(0xFF000000); // 트루 블랙 — 카메라 프리뷰 뒤
  static const surface = Color(0xFF101310); // 살짝 띄운 면
  static const surfaceMuted = Color(0xFF333B36); // 링 트랙/입력 — 아래 주석 참조
  static const border = Color(0xFF39423D); // 뷰파인더/카드 경계
  static const foreground = Color(0xFFFFFFFF); // 검정 위 21:1 AAA
  static const foregroundMuted = Color(0xFF9EA9A3); // 검정 위 8.66:1 AAA
  // surfaceMuted는 검정 대비 1.9:1이다. workout의 FormScoreRing 트랙이 이 색인데,
  // 3:1로 올리려면 #565C57까지 밝혀야 하고 그러면 입력 필드 위 foregroundMuted가 4.5:1을
  // 못 넘긴다. 트랙은 1.4.11의 "이해에 필요한 그래픽 객체"가 아니다 — 점수는 링 중앙에
  // 숫자로, 크기는 채움 호(scoreColor, 검정 위 13.9:1)로 이미 전달된다. 의도된 예외다.
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
/// 60(배경): scaffold는 딥다크/트루블랙 단색. **여기 있는 색을 scaffold에 쓰지 마라.**
/// 30(색면): 카드 단위로 배경색을 통째로 바꾼다 — 중립 다크 패널부터 라임 솔리드까지.
/// 10(액센트): [AppColors.primary] (Lime) — 큰 숫자·CTA·기록일.
///
/// **슬롯 이름은 구 팔레트(네이비/크림슨/고추장/크림)에서 그대로 물려받았다.**
/// 화면 6개가 이 이름을 참조하므로 이름을 유지하고 값만 갈아끼웠다. 새 의미는 각 슬롯 주석에.
///
/// 슬롯 배치를 결정한 것은 `calendar.dart`의 히트맵이다 —
/// `cream(0) → tintGochujang(1) → crimson(2) → gochujang(3)` 순으로 농도를 읽으므로
/// 이 4개는 **휘도가 단조 증가하는 그린 램프**여야 한다(0.010 < 0.056 < 0.123 < 0.646).
/// 나머지 3개(navy/tintNavy/tintCrimson)는 램프 밖의 중립·보조 패널이다.
class AppBlocks {
  AppBlocks._();

  /// 어두운 그린 패널(tintCrimson/tintGochujang) 공통 보조 톤 — 해당 배경에서 6.39:1.
  static const _greenPanelMuted = Color(0xFFC2D6AC);

  /// 중립 다크 패널 공통 보조 톤 — cream/tintNavy 배경에서 6.5:1 이상.
  static const _neutralPanelMuted = Color(0xFF9EA9A3);

  // --- 솔리드 색면 ---

  /// 구 Cosmos Blue 자리 → **중립 다크 패널**. 그린 램프 밖의 "쉼표" 카드.
  /// `home`의 색면 사이클, `summary`의 무난/점수없음 밴드, `calendar` 시트 배경에 쓰인다.
  static const navy = BlockStyle(
    background: Color(0xFF272E2A), // 중립 다크 (그린 램프에 속하지 않음)
    foreground: Color(0xFFF1F5F2), // 12.63:1 AAA
    muted: Color(0xFFA0ABA5), // 5.87:1 AA
  );

  /// 구 Crimson Blaze 자리 → **미드 그린**(히트맵 lv2). 라임 솔리드 바로 아래 단계.
  static const crimson = BlockStyle(
    background: Color(0xFF3F6E1A), // 미드 그린
    foreground: Color(0xFFF1F5F2), // 5.52:1 AA
    muted: Color(0xFFD9EAC6), // 4.78:1 AA (구 팔레트에선 muted가 불가능했으나 이제 가능)
  );

  /// 구 Gochujang Red 자리 → **라임 액센트 솔리드**(히트맵 lv3). 팔레트의 10.
  /// 유일하게 전경이 어두운 색면이다 — 위 텍스트는 반드시 이 foreground를 쓴다.
  static const gochujang = BlockStyle(
    background: Color(0xFFA3E635), // Lime Accent = AppColors.primary
    foreground: Color(0xFF0A1400), // 12.51:1 AAA
    muted: Color(0xFF2C4A08), // 6.66:1 AA
  );

  /// 구 Varden Cream 자리 → **기본 다크 카드면**(히트맵 lv0 = 기록 없음).
  /// 값이 [AppColors.surface]와 같다 — 일반 카드와 색면 카드가 같은 면을 공유한다.
  /// scaffold 대비 1.10:1이므로 사용처에서 `outlined: true`가 여전히 필요하다.
  static const cream = BlockStyle(
    background: AppColors.surface, // #161A17
    foreground: Color(0xFFF1F5F2), // 15.98:1 AAA
    muted: _neutralPanelMuted, // 7.25:1 AAA
  );

  // --- 소프트 틴트 색면 ---

  /// 구 tintNavy 자리 → **가장 낮은 중립 틴트**. `profile`의 outlined 카드용.
  static const tintNavy = BlockStyle(
    background: Color(0xFF1D2320),
    foreground: Color(0xFFF1F5F2), // 14.53:1 AAA
    muted: _neutralPanelMuted, // 6.59:1 AA
  );

  /// 구 tintCrimson 자리 → **딤 그린 틴트**. `profile`의 StreakBadge·outlined 카드용.
  /// [tintGochujang]과 값이 같다 — 아래 주석 참조.
  static const tintCrimson = BlockStyle(
    background: Color(0xFF2E4A1C),
    foreground: Color(0xFFF1F5F2), // 9.03:1 AAA
    muted: _greenPanelMuted, // 6.39:1 AA
  );

  /// 구 tintGochujang 자리 → **딤 그린 틴트**(히트맵 lv1).
  /// [tintCrimson]과 **의도적으로 같은 값**이다. 구 팔레트는 크림슨/고추장이라는 서로 다른
  /// 두 색상(hue)의 틴트였지만 새 팔레트의 액센트는 라임 하나뿐이라, 둘 다 "딤 그린 틴트"라는
  /// 같은 역할로 수렴한다. 억지로 명도를 벌리면 히트맵 lv0~lv2 사이 간격이 무너진다.
  static const tintGochujang = BlockStyle(
    background: Color(0xFF2E4A1C),
    foreground: Color(0xFFF1F5F2), // 9.03:1 AAA
    muted: _greenPanelMuted, // 6.39:1 AA
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
  // secondary(앰버)/tertiary(라임)/error(소프트 레드)는 전부 **밝은** 액센트다.
  // 그 위 전경은 어두워야 대비가 산다 → 세 자리 모두 onPrimary(#0A1400)를 쓴다.
  // (라임 위 12.51:1 / 앰버 위 14.5:1 / 소프트 레드 위 7.33:1)
  final onAccent = onPrimary;

  final colorScheme = ColorScheme(
    brightness: Brightness.dark, // 두 세트 모두 다크
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

  // 다크 위 그림자는 면 분리에 거의 기여하지 않는다 — 순검정으로 낮게 깔고
  // 면 구분은 surface 계단(scaffold→surface→surfaceMuted)과 outlined 보더가 담당한다.
  final shadow = Colors.black.withValues(alpha: 0.5);

  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
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
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: border, width: 1),
      ),
      margin: EdgeInsets.zero,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: surface,
      // 다크면 위에서 알파 0.22는 1.73:1로 인디케이터 알약이 사라졌다.
      // 0.45면 surface 대비 3.35:1(1.4.11 충족)이고, 그 위 선택 아이콘(primary)도 3.48:1로 뜬다.
      indicatorColor: primary.withValues(alpha: 0.45),
      surfaceTintColor: Colors.transparent,
      elevation: 1,
      shadowColor: shadow,
      labelTextStyle: WidgetStateProperty.resolveWith((states) => TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: states.contains(WidgetState.selected) ? primary : foregroundMuted,
          )),
      iconTheme: WidgetStateProperty.resolveWith((states) => IconThemeData(
            color: states.contains(WidgetState.selected) ? primary : foregroundMuted,
          )),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: primary,
        foregroundColor: onPrimary,
        minimumSize: const Size.fromHeight(52),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: foreground,
        // 경계는 장식이 아니라 조작 가능 영역 표시 → 배경 대비 3:1 이상인 primary 계열을 옅게.
        // 일반 0.55 → 딥다크 위 4.49:1, workout 0.7 → 검정 위 6.84:1 (둘 다 1.4.11 충족).
        side: BorderSide(color: primary.withValues(alpha: dark ? 0.7 : 0.55), width: 1.5),
        minimumSize: const Size.fromHeight(52),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: primary, // 두 세트 다 다크 → 라임이 양쪽에서 7:1 이상
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
      labelStyle: TextStyle(color: foregroundMuted),
      hintStyle: TextStyle(color: foregroundMuted),
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
      actionTextColor: primary, // surfaceMuted 위 8.72:1 AAA
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
      title: 'Hohowatt',
      theme: buildAppTheme(dark: false),
      home: Api.instance.isLoggedIn ? const RootScreen() : const LoginScreen(),
    );
  }
}
