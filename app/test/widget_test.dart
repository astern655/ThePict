import 'package:flutter_test/flutter_test.dart';
import 'package:app/main.dart';

void main() {
  testWidgets('로그인 화면이 기본으로 표시된다', (tester) async {
    await tester.pumpWidget(const HohowattApp());
    expect(find.text('로그인'), findsWidgets);
  });
}
