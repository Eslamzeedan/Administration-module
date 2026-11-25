import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:eup_mobile/main.dart';

void main() {
  testWidgets('employee and driver entry points', (tester) async {
    await tester.pumpWidget(const FleetApp());
    expect(find.text('الرحلات'), findsOneWidget);
    expect(find.text('خدمات الموظف'), findsOneWidget);
    expect(find.byType(ListTile), findsNWidgets(2));
  });
  test('navigation stays on configured origin', () {
    final site=Uri.parse('https://stage.example.test');
    expect(sameSite(site,'https://stage.example.test/login'),isTrue);
    for (final url in ['https://stage.example.test.evil.test','http://stage.example.test','https://stage.example.test:8443','file:///tmp/file']) {
      expect(sameSite(site,url),isFalse);
    }
  });
}
