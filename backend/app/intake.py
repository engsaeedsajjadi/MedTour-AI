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
