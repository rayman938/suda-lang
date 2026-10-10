# سُدى | Suda

سُدى نواة لغة برمجة عربية صغيرة تعمل محليًا. الإصدار الحالي 0.4.0 ويتضمن محللًا
للنص العربي، محللًا نحويًا، مولّد bytecode، آلة افتراضية محدودة الموارد،
واجهة سطر أوامر، قوائم وقواميس قابلة للتغيير، أدوات للمجموعات، `اكسر` و`استمر`,
اختبارات، ودليلًا عربيًا.

هذه النسخة **نموذج أولي تنفيذي** وليست مترجمًا أصليًا إلى كود الآلة، ولا تدّعي
أنها أسرع من Python أو أنها تنتج تطبيقات Android أو iOS أو الويب. حدود الإصدار
والميزات المخطط لها موضحة في الدليل العربي الموحد. الآلة الافتراضية مبنية على Python؛
وهي للتعلّم والتحقق من تصميم اللغة، لا لادعاء أداء منخفض المستوى.

## حقوق اللغة

المستودع عام للعرض، لكن اللغة **ليست مفتوحة المصدر**. جميع الحقوق محفوظة
لمؤلف ومالك سُدى؛ ولا يمنح هذا المستودع إذنًا بإعادة استخدام الشيفرة أو
تعديلها أو إعادة توزيعها أو نسب اللغة إلى شخص آخر. راجع ملف [LICENSE](LICENSE).
الحماية القانونية لا تمنع الفحص التقني المطلق ولا تتغلب على الاستثناءات
الإلزامية في القوانين المحلية؛ لا تنشر أسرارًا أو بيانات لا تريد كشفها في
مستودع عام.

## متطلبات التشغيل

- Python 3.11 أو أحدث
- لا توجد تبعيات تشغيل خارجية

## تثبيت وتشغيل

تثبيت الإصدار المنشور مباشرة من GitHub بأمر واحد:

```powershell
python -m pip install "git+https://github.com/rayman938/suda-lang.git"
```

يتطلب Python 3.11 أو أحدث وGit، ويثبت حزمة المترجم من GitHub مباشرة.
ولتثبيت نسخة منشورة على PyPI (بعد إصدارها هناك) استخدم:

```powershell
python -m pip install suda-lang
```

لتنزيل المشروع كاملًا مع الأمثلة والدليل، نفّذ:

```powershell
git clone https://github.com/rayman938/suda-lang.git
cd suda-lang
python -m pip install .
suda run examples\مرحبا.sada
```

أما تثبيت البرنامج فقط من أي مجلد، فأمر `pip install` أعلاه يكفي.

ومن دون تثبيت الحزمة:

```powershell
$env:PYTHONPATH = "src"
python -m suda run examples\مرحبا.sada
```

أوامر أخرى:

```powershell
python -m suda check examples\حساب.sada
python -m suda compile examples\حساب.sada -o build\حساب.sbc
python -m suda disassemble build\حساب.sbc
python -m suda run-bytecode build\حساب.sbc
python -m suda run examples\المخزون.sada
```

لتقليل حجم ملف bytecode، أضف `--compress` إلى أمر `compile`. يستخدم الملف
المضغوط zlib، ويكتشفه المشغّل تلقائيًا؛ أما JSON غير المضغوط فيبقى مدعومًا:

```powershell
suda compile examples\حساب.sada -o build\حساب.sbc --compress
suda run-bytecode build\حساب.sbc
```

يتضمن `examples\المخزون.sada` برنامجًا يتعامل مع قوائم القواميس، كما يعرض
`examples\فرز.sada` الفرز الفقاعي وتحديث عناصر القائمة.

شغّل الاختبارات:

```powershell
python -m unittest discover -s tests -v
```

شغّل مقارنة زمنية قابلة لإعادة الإنتاج، من دون افتراض أي نتيجة مسبقًا:

```powershell
python benchmarks\benchmark.py --items 1000 --rounds 15 --warmup 3
```

مرجع النحو والمكتبة والأمان والأمثلة وخارطة التطوير كلها في
[`docs/دليل-لغة-سدى.md`](docs/دليل-لغة-سدى.md). مستودع GitHub:
https://github.com/rayman938/suda-lang
