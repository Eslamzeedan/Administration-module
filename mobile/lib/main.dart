import 'package:flutter/foundation.dart';
import 'package:material_ui/material_ui.dart';
import 'package:webview_flutter/webview_flutter.dart';

void main() => runApp(const FleetApp());

bool sameSite(Uri site, String address) {
  final target = Uri.tryParse(address);
  return target != null && target.scheme == site.scheme && target.host == site.host &&
      target.port == site.port && target.userInfo.isEmpty;
}

class FleetApp extends StatelessWidget {
  const FleetApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'EuP Administration', debugShowCheckedModeBanner: false,
    theme: ThemeData(colorSchemeSeed: const Color(0xff146655), useMaterial3: true),
    builder: (context, child) => Directionality(textDirection: TextDirection.rtl, child: child!),
    home: const Home(),
  );
}

class Home extends StatelessWidget {
  const Home({super.key});
  static final site = Uri.parse(const String.fromEnvironment('SITE_URL',
      defaultValue: 'http://192.168.64.110:8004'));
  void open(BuildContext context, String title, String route) {
    if (site.scheme != 'https' && !(kDebugMode && site.origin == 'http://192.168.64.110:8004')) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('يلزم عنوان HTTPS لهذه النسخة')));
      return;
    }
    Navigator.push(context, MaterialPageRoute<void>(builder: (_) => Portal(title, site, route)));
  }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('EuP Egypt')),
    body: ListView(padding: const EdgeInsets.all(20), children: [
      Text('خدمات الإدارة', style: Theme.of(context).textTheme.headlineMedium),
      const SizedBox(height: 20),
      Card(child: ListTile(leading: const Icon(Icons.route), title: const Text('الرحلات'),
        subtitle: const Text('اطلب عربية أو تابع مشاويرك كسائق'), trailing: const Icon(Icons.chevron_left),
        onTap: () => open(context,'الرحلات','/administration_trips'))),
      Card(child: ListTile(leading: const Icon(Icons.assignment_outlined), title: const Text('خدمات الموظف'),
        subtitle: const Text('تقديم الطلبات ومتابعة حالتها'), trailing: const Icon(Icons.chevron_left),
        onTap: () => open(context,'خدمات الموظف','/administration_self_service'))),
      if (kDebugMode) const Padding(padding: EdgeInsets.only(top:20),child: Text('نسخة الاختبار تتطلب الاتصال بشبكة الشركة.')),
    ]),
  );
}

class Portal extends StatefulWidget {
  final String title, route;
  final Uri site;
  const Portal(this.title,this.site,this.route,{super.key});
  @override
  State<Portal> createState() => _PortalState();
}

class _PortalState extends State<Portal> {
  late final WebViewController web;
  int progress = 0;
  bool failed = false;
  @override
  void initState() {
    super.initState();
    web = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onNavigationRequest: (r) => sameSite(widget.site,r.url) ? NavigationDecision.navigate : NavigationDecision.prevent,
        onPageStarted: (_) { if (mounted) { setState(() { failed=false; progress=0; }); } },
        onProgress: (p) { if (mounted) { setState(() => progress=p); } },
        onWebResourceError: (e) { if (mounted && e.isForMainFrame == true) { setState(() => failed=true); } },
      ))
      ..loadRequest(widget.site.resolve(widget.route));
  }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.title), actions: [
      IconButton(tooltip:'رجوع داخل الصفحة',icon:const Icon(Icons.undo),onPressed: () async {
        if (await web.canGoBack()) { await web.goBack(); } else if (context.mounted) { Navigator.pop(context); }
      }),
      IconButton(tooltip:'تسجيل الخروج',icon:const Icon(Icons.logout),onPressed: () async {
        await web.loadRequest(widget.site.resolve('/?cmd=web_logout'));
        await WebViewCookieManager().clearCookies();
        await web.clearLocalStorage();
        if (context.mounted) { Navigator.pop(context); }
      }),
    ]),
    body: SafeArea(child: Column(children:[
      if (progress < 100 && !failed) LinearProgressIndicator(value:progress/100),
      Expanded(child: failed ? Center(child: Column(mainAxisSize: MainAxisSize.min,children:[
        const Text('تعذر الاتصال بالموقع. تحقق من اتصال الشبكة.'),
        TextButton(onPressed:()=>web.loadRequest(widget.site.resolve(widget.route)),child:const Text('إعادة المحاولة')),
      ])) : WebViewWidget(controller:web)),
    ])),
  );
}
