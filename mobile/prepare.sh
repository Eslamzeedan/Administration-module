#!/usr/bin/env bash
set -euo pipefail
src="$(cd "$(dirname "$0")" && pwd)"
out=${1:?Supply a new build directory}
test ! -e "$out"
flutter create --platforms=android,ios --org com.eupegypt --project-name eup_mobile "$out"
cd "$out"
cp "$src/lib/main.dart" lib/main.dart
rm test/widget_test.dart
cp "$src/test/mobile_test.dart" test/
flutter pub add webview_flutter:4.14.1
python3 - <<'PY'
from pathlib import Path
main=Path('android/app/src/main/AndroidManifest.xml')
s=main.read_text().replace('<application','<uses-permission android:name="android.permission.INTERNET"/>\n    <application',1).replace('android:label="eup_mobile"', 'android:label="EuP Administration"')
main.write_text(s)
d=Path('android/app/src/debug/AndroidManifest.xml')
d.write_text(d.read_text().replace('</manifest>', '<application android:networkSecurityConfig="@xml/stage_network" /></manifest>'))
r=Path('android/app/src/debug/res/xml/stage_network.xml')
r.parent.mkdir(parents=True,exist_ok=True)
r.write_text('<network-security-config><base-config cleartextTrafficPermitted="false"/><domain-config cleartextTrafficPermitted="true"><domain>192.168.64.110</domain></domain-config></network-security-config>')
PY
dart format lib/main.dart test/mobile_test.dart
flutter analyze
flutter test
flutter build apk --debug
