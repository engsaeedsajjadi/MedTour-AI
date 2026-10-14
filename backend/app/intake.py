"""Non-diagnostic, deterministic initial intake texts. Not a medical decision system."""
from __future__ import annotations
from pydantic import BaseModel, Field

LANGUAGES = {'fa','ar','en','ps','prs'}
PROMPTS = {
 'fa': ['برای شروع، رضایت خود را برای ثبت اطلاعات اولیه اعلام کنید.', 'مشکل یا خدمت پزشکی موردنظر را توضیح دهید.', 'آیا گزارش یا آزمایش قبلی دارید؟ لطفاً از پرتال امن استفاده کنید.'],
 'ar': ['يرجى الموافقة على جمع معلومات الاستقبال الأولية.', 'ما الخدمة الطبية التي تحتاج إليها؟', 'هل لديك تقارير طبية سابقة؟ يرجى استخدام البوابة الآمنة.'],
 'en': ['Please confirm consent for collecting initial intake details.', 'What medical service do you need?', 'Do you have prior medical reports? Please use our secure portal.'],
 'ps': ['مهرباني وکړئ د لومړنیو معلوماتو د راټولولو لپاره رضايت ورکړئ.', 'تاسو کومو طبي خدماتو ته اړتیا لرئ؟', 'آیا مخکیني طبي راپورونه لرئ؟ مهرباني وکړئ خوندي پورټل وکاروئ.'],
 'prs': ['لطفاً رضایت خود را برای ثبت معلومات ابتدایی اعلام کنید.', 'به کدام خدمات صحی نیاز دارید؟', 'آیا گزارش‌های طبی قبلی دارید؟ لطفاً از پورتال مصون استفاده کنید.'],
}
EMERGENCY = {
 'en': ('chest pain','cannot breathe','severe bleeding','stroke symptoms','unconscious'),
 'fa': ('درد قفسه سینه','تنگی نفس شدید','خونریزی شدید','بیهوش'),
 'ar': ('ألم في الصدر','نزيف شديد','ضيق تنفس شديد','فاقد الوعي'),
 'ps': ('د سینې درد','سخت ساه لنډي','شدیده وینه بهیدنه'),
 'prs': ('درد قفسه سینه','نفس‌تنگی شدید','خونریزی شدید','بیهوش'),
}
EMERGENCY_RESPONSE = {
 'fa': 'این پیام ممکن است نشان‌دهنده وضعیت اورژانسی باشد. همین حالا با خدمات اورژانس محل خود تماس بگیرید. این سامانه خدمات اورژانس یا تشخیص پزشکی ارائه نمی‌کند.',
 'ar': 'قد تشير رسالتك إلى حالة طارئة. اتصل بخدمات الطوارئ المحلية فورًا. هذه الخدمة لا تقدم التشخيص أو الطوارئ.',
 'en': 'Your message may describe an emergency. Contact local emergency services immediately. This service does not provide emergency care or diagnosis.',
 'ps': 'ستاسو پیغام ښايي بیړني حالت ته اشاره وکړي. سمدستي د خپل ځای له بیړنیو خدماتو سره اړیکه ونیسئ. دا خدمت بیړنۍ درملنه نه وړاندې کوي.',
 'prs': 'پیام شما ممکن است نشان‌دهنده حالت عاجل باشد. فوراً با خدمات عاجل محل تماس بگیرید. این سامانه خدمات عاجل ارائه نمی‌کند.',
}
class IntakeAnswer(BaseModel):
    language: str = Field(default='en')
    message: str = Field(min_length=1,max_length=4000)

def intake_response(language: str,message:str)->dict:
    lang=language if language in LANGUAGES else 'en'
    flagged=any(term.casefold() in message.casefold() for words in EMERGENCY.values() for term in words)
    return {'language':lang,'emergency_keyword_detected':flagged,
        'human_review_required':True,
        'message':EMERGENCY_RESPONSE[lang] if flagged else PROMPTS[lang][1],
        'disclaimer':'Automated text-routing only, not medical triage, medical advice, or diagnosis.'}

# Distinct questionnaire copy per locale, reviewed by coordinators before use.
# These prompts are administrative, not a diagnostic decision tree.
QUESTION_KEYS=('service_request','age_range','existing_diagnosis','previous_consultation','existing_reports')
INTAKE_QUESTIONS={
 'en':('What medical service are you looking for?', 'What is the patient’s age range?',
       'Has a physician already given a diagnosis? You may answer no or unknown.',
       'Have you consulted a healthcare professional about this concern?',
       'Do you have earlier medical reports? Use the secure document portal for uploads.'),
 'fa':('چه نوع خدمات پزشکی نیاز دارید؟','بازه سنی بیمار چقدر است؟',
       'آیا قبلاً پزشک تشخیصی ثبت کرده است؟ می‌توانید خیر یا نامشخص پاسخ دهید.',
       'آیا درباره این موضوع با پزشک مشورت کرده‌اید؟',
       'آیا مدارک پزشکی قبلی دارید؟ فقط از پرتال امن استفاده کنید.'),
 'ar':('ما الخدمة الطبية التي تبحث عنها؟','ما الفئة العمرية للمريض؟',
       'هل سبق للطبيب تقديم تشخيص؟ يمكنك الإجابة بلا أو غير معروف.',
       'هل استشرت طبيباً بخصوص هذه الحالة؟',
       'هل لديك تقارير طبية سابقة؟ استخدم البوابة الآمنة للرفع.'),
 'ps':('تاسو د کوم ډول طبي خدمت غوښتنه لرئ؟','د ناروغ د عمر حدود څومره دي؟',
       'آیا ډاکټر مخکې تشخیص ورکړی؟ تاسو کولی شئ نه یا نه پوهېږم ووایاست.',
       'آیا د دې ستونزې په اړه مو له ډاکټر سره سلا کړې ده؟',
       'آیا مخکېني طبي راپورونه لرئ؟ یوازې خوندي پورټل وکاروئ.'),
 'prs':('به کدام خدمات صحی ضرورت دارید؟','محدوده سن مریض چقدر است؟',
        'آیا داکتر قبلاً تشخیصی ارائه کرده است؟ می‌توانید نخیر یا نامعلوم بگویید.',
        'آیا برای این مشکل با داکتر مشوره کرده‌اید؟',
        'آیا راپورهای طبی قبلی دارید؟ لطفاً از پورتال مصون استفاده کنید.'),
}

def next_question(lang:str,stage:int)->str|None:
    if lang not in LANGUAGES:raise ValueError('Unsupported language')
    if stage<0 or stage>len(QUESTION_KEYS):raise ValueError('Invalid stage')
    return INTAKE_QUESTIONS[lang][stage] if stage<len(QUESTION_KEYS) else None
