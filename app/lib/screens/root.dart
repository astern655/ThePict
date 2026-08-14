import 'package:flutter/material.dart';
import '../main.dart';
import 'calendar.dart';
import 'home.dart';
import 'profile.dart';

/// 하단 탭 셸 — 홈/캘린더/프로필 (iOS 톤 탭바).
/// 기존 화면 위젯을 그대로 재사용하고 IndexedStack으로 각 탭 상태를 유지한다.
class RootScreen extends StatefulWidget {
  const RootScreen({super.key});

  @override
  State<RootScreen> createState() => _RootScreenState();
}

class _RootScreenState extends State<RootScreen> {
  int _index = 0;

  static const _tabs = [HomeScreen(), CalendarScreen(), ProfileScreen()];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _tabs),
      // 플랫 iOS 탭바(시안 The Fit iOS): 솔리드 흰 면 + 0.5dp 상단 헤어라인. 블러·백드롭 없음.
      // 면 분리는 그림자가 아니라 선(헤어라인)으로 — 시안 border-top .5px와 정렬.
      // 선택 탭은 코랄(테마 navigationBarTheme: primary@0.20 알약 + link 아이콘/라벨),
      // 비선택은 회색(foregroundMuted) — 값은 전부 테마에서 온다.
      bottomNavigationBar: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 0.5dp 헤어라인 — iOS separator.
          const SizedBox(
            height: 0.5,
            width: double.infinity,
            child: ColoredBox(color: AppColors.border),
          ),
          NavigationBar(
            elevation: 0,
            backgroundColor: AppColors.surface, // 솔리드 흰 면(시안 --color-surface)
            surfaceTintColor: Colors.transparent,
            selectedIndex: _index,
            onDestinationSelected: (i) => setState(() => _index = i),
            destinations: const [
              NavigationDestination(
                  icon: Icon(Icons.home_outlined),
                  selectedIcon: Icon(Icons.home),
                  label: '홈'),
              NavigationDestination(
                  icon: Icon(Icons.calendar_month_outlined),
                  selectedIcon: Icon(Icons.calendar_month),
                  label: '캘린더'),
              NavigationDestination(
                  icon: Icon(Icons.person_outline),
                  selectedIcon: Icon(Icons.person),
                  label: '프로필'),
            ],
          ),
        ],
      ),
    );
  }
}
