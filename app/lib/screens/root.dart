import 'package:flutter/material.dart';
import 'calendar.dart';
import 'home.dart';
import 'profile.dart';

/// 하단 탭 셸 — 홈/캘린더/프로필 (Material 3 NavigationBar, 토스 스타일).
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
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: '홈'),
          NavigationDestination(
              icon: Icon(Icons.calendar_month_outlined),
              selectedIcon: Icon(Icons.calendar_month),
              label: '캘린더'),
          NavigationDestination(
              icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: '프로필'),
        ],
      ),
    );
  }
}
