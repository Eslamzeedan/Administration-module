# دليل ترقية EuP Administration إلى v2 والرجوع

هذه خطوات ينفذها مسؤول الـbench يدويًا. لم تُنفذ على أي سيرفر. النسخة تحتاج قبول staging أولًا، وأي تغيير على الإنتاج يحتاج موافقة صريحة من مالك النظام.

## 1. تجهيز واختيار المسار الصحيح

- الإنتاج المعروف: erpnext-v16.eup-cairo.local، والـbench: /home/frappe/frappe-bench.
- التطبيق المعروف: /home/frappe/eup_administration، ورابطه داخل apps/eup_administration. تحقق من المسارات الفعلية قبل النسخ.
- استخدم staging في bench مستقل، بكود مستقل لا يشير إلى مسار تطبيق الإنتاج. كل مواقع الـbench تشترك في نفس الكود، وحتى bench آخر مرتبط بنفس مجلد التطبيق ليس معزولًا.
- احتفظ بإصدارات Frappe وERPNext v16 الحالية؛ لا تجمع ترقيتهما مع هذه الترقية. قاعدة البيانات المطلوبة MariaDB/InnoDB.
- قارن كود السيرفر بالـZIP الأصلي قبل الاستبدال. النسخة مبنية من الملف المرفق؛ أي تغييرات إضافية موجودة على السيرفر تحتاج دمجًا ومراجعة.
- سجّل bench version، التطبيقات المثبتة، التعديلات المحلية، صلاحيات الأدوار وCustom DocPerm، إعداد timezone، وتخصيص Workspace.
- ضع محتويات مجلد eup_administration-v2 المستخرج في مجلد إصدار جديد، مثل /home/frappe/releases/eup_administration-v2.

## 2. نسخة احتياطية متسقة

قبل استبدال الكود، ضع الموقع في maintenance mode، أوقف scheduler، امنع المستخدمين/التكاملات من الكتابة، وصفّ أو أوقف workers التابعة للـbench باستخدام مدير العمليات الحالي. إذا كانت هناك مواقع أخرى تشارك الكود، خطط لتوقفها واختبارها أيضًا. لا تكتفِ بإيقاف واجهة الموقع مع بقاء وظائف الخلفية تكتب.

نفّذ من الـbench المقصود، وبمستخدم frappe. مثال staging فقط؛ غيّر الاسم والمسارات إلى قيم مؤكدة:

```bash
cd /home/frappe/STAGING_BENCH
SITE=YOUR_STAGING_SITE
bench --site "$SITE" set-maintenance-mode on
bench --site "$SITE" disable-scheduler
bench version
bench --site "$SITE" list-apps
bench --site "$SITE" backup --with-files --ignore-backup-conf
readlink -f apps/eup_administration
```

احتفظ بملفات النسخة التي طبعها الأمر: قاعدة البيانات، public files، private files، site_config.json ومفتاح encryption_key، وإعدادات common_site_config ومدير العمليات. انسخها لمكان خارج مجلد الكود واحسب SHA256. خذ أيضًا أرشيفًا كاملًا للكود الحقيقي قبل التغيير، بما فيه .git وأي تعديلات غير committed. اختبر استعادة هذه النسخة على staging؛ مجرد نجاح إنشاء backup لا يثبت صلاحية الرجوع.

## 3. تجربة الترقية على نسخة من البيانات

استعد نسخة البيانات على bench staging مستقل مثبت عليه نفس إصدارات التطبيقات. عطّل إرسال البريد والتكاملات الخارجية من هذه النسخة، واترك scheduler متوقفًا. ثبّت حزمة v2 بدل كود التطبيق الحالي في staging فقط. مثال نسخ يحافظ على .git والمسار الرابط:

```bash
cd /home/frappe/STAGING_BENCH
APP_REAL="$(readlink -f apps/eup_administration)"
# راجع APP_REAL وتأكد أنه مجلد staging مستقل قبل متابعة النسخ.
rsync -a --exclude=.git --exclude=__pycache__ /home/frappe/releases/eup_administration-v2/ "$APP_REAL/"
./env/bin/pip install --no-deps -e "$APP_REAL"
```

لا تستخدم --delete، ولا تمسح التطبيق، ولا تغير الرابط الرمزي إلى مسار الإنتاج، ولا تستخدم uninstall-app أو reset-perms. لا تنفذ install-app على موقع مثبت عليه التطبيق بالفعل. بالنسبة لتثبيت جديد على staging فارغ: أضف التطبيق إلى الـbench بالطريقة المعتادة ثم install-app مرة واحدة بعد وجود ERPNext.

قبل migrate، والكود الجديد موجود مع استمرار وقف الكتابة، التقط snapshot. الأداة تقرأ الحقول القديمة فقط وتعمل قبل إضافة المخطط الجديد. وجود الكود الجديد وحده لا يغير بيانات الموقع:

```bash
bench --site "$SITE" execute eup_administration.deployment.snapshot > /home/frappe/adm-v2-before.json
bench --site "$SITE" migrate
bench build --app eup_administration
bench --site "$SITE" clear-cache
bench --site "$SITE" execute eup_administration.deployment.snapshot > /home/frappe/adm-v2-after.json
./env/bin/python "$APP_REAL/tools/compare_snapshots.py" /home/frappe/adm-v2-before.json /home/frappe/adm-v2-after.json
```

يجب نجاح المقارنة: نفس عدد وبصمة الحقول الأصلية في DocTypes الخمسة، نفس الصلاحيات الأصلية، والحفاظ على محتوى Workspace الموجود. لو Workspace كان مفقودًا قبل الترقية يُنشأ افتراضيًا؛ التخصيص المفقود يحتاج backup أقدم.

شغّل migrate مرة ثانية، والتقط snapshot ثانية وقارنها بالأصل قبل فتح الكتابة. هذا يكشف حذف Workspace أثناء migrate التالي أو مشكلة عدم قابلية تكرار patches. بعد ذلك أعد تشغيل عمليات staging وافتحه للاختبار حسب [STAGING_ACCEPTANCE.md](STAGING_ACCEPTANCE.md).

## 4. ماذا تفعل migrations؟

- pre_model_sync: يتأكد من الأدوار، ويعتبر Workspace القديم سجلًا مملوكًا للموقع (standard=0) لأنه كان يُنشأ أثناء التشغيل بدون ملف مصدر. لا يستبدل محتواه.
- إضافة حقول للمركبة والرحلة والحجز، مع الاحتفاظ بالحقول والأسماء وأنماط تسمية السجلات الحالية. لا حذف ولا إعادة تسمية للجداول الحالية.
- DocTypes جديدة للوقود والمصاريف والصيانة وخدمات الاجتماعات، مع Dashboard وتقارير وWorkspace v2 بملف مصدر.
- post_model_sync: يملأ شركة الحجز من غرفة الاجتماع فقط حيث الحقل الجديد فارغ، ويضيف indexes للتعارضات والتكرار. لا يعيد كتابة العدادات أو الرحلات القديمة.
- لا reset للصلاحيات المخصصة، ولا developer mode. كتابة SQL أثناء migrations قد تُنفذ DDL بعمليات commit ضمنية؛ backup الكامل هو أساس الرجوع.
- سبب حذف Workspace على سيرفرك لا يمكن إثباته بدون log وإصدار Frappe الفعلي. علاج النسخة يجمع حفظ القديم مع ملف مصدر للـWorkspace الجديد.

## 5. الإنتاج بعد قبول staging وموافقة المالك

استخدم نفس الحزمة وبصمتها ونفس خطوات النسخ الاحتياطي/تجميد الكتابة/snapshot/migrate/build/المقارنة التي نجحت على staging. تحقق مجددًا من المسار /home/frappe/frappe-bench/apps/eup_administration ومن الهدف /home/frappe/eup_administration؛ لا تستبدل الرابط نفسه. أعد تشغيل خدمات الـbench بمدير العمليات الحالي بعد انتهاء build. اختبر دخول المدير والسائق وإجراءات الرحلة والحجز والتقارير قبل فتح النظام للجميع. أعد scheduler إلى حالته السابقة فقط. لا تفتح الإنتاج إذا أخفقت المقارنة أو أي اختبار حرج.

## 6. Rollback

نافذة الرجوع الأفضل: الكتابة ما زالت متوقفة ولم يُسمح بمعاملات جديدة على v2. لا تعتبر إعادة ملفات v0.1.0 وحدها rollback كاملًا؛ بقاء DocTypes/Workspaces الجديدة بدون كود مصدر قد يسبب orphan cleanup أو أخطاء تحميل.

1. أبقِ maintenance mode وإيقاف scheduler/workers. احفظ logs والحالة الفاشلة في نسخة منفصلة للتحقيق.
2. أعد الكود الفعلي من أرشيف ما قبل الترقية، مع نفس رابط التطبيق وإصدارات Frappe/ERPNext السابقة. أعد تثبيت editable package إذا تغير المسار.
3. استعد قاعدة البيانات وملفات public/private ومفتاح/إعدادات الموقع من **نفس** backup المتسق. أمر نموذجي على الموقع المقصود، بعد مراجعة paths ونقاط الاستعادة:

```bash
bench --site "$SITE" restore /ABS/BACKUP/database.sql.gz --with-public-files /ABS/BACKUP/public-files.tar --with-private-files /ABS/BACKUP/private-files.tar
bench build --app eup_administration
bench --site "$SITE" clear-cache
```

4. استخدم صيغ الملفات الفعلية التي أنتجها backup (قد تكون tar أو tgz أو ملفات مشفرة)، وأدخل مفاتيح التشفير/صلاحيات قاعدة البيانات محليًا حسب إعدادك. لا تنشر الأسرار في المحادثات أو ملفات التسليم.
5. أعد تشغيل العمليات، تحقق من عدد السجلات والعدادات والصلاحيات وWorkspace مقابل baseline، ثم افتح الكتابة وأعد scheduler إلى حالته السابقة. لا تشغّل migrate بكود قديم على قاعدة بيانات v2 قبل استعادتها.
6. إذا دخلت بيانات جديدة بعد تشغيل v2، فإن استعادة backup القديم تفقدها. أوقف الكتابة واحفظ نسخة كاملة من حالة v2، واستخرج فروق المعاملات ووافق على تسويتها قبل الاستعادة؛ لا توجد عملية downgrade آلية مضمونة لهذه الحالة.
