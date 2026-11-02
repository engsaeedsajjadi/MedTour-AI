/** Personal and organization settings shared by the panel. Cached per browser tab only. */
import {request} from './api';

export type Session={started_at:string;last_used_at:string;expires_at:string;two_factor:boolean};
export type Profile={email:string;role:string;organization_slug:string;display_name:string;timezone:string;
 calendar:'jalali'|'gregorian';digits:'persian'|'latin';start_page:string;
 two_factor_enabled:boolean;two_factor_required:boolean;sessions:Session[]};
export type Organization={display_name:string;contact_email:string;contact_phone:string;website:string;
 privacy_notice_url:string;patient_support_hours:string;default_language:string;enabled_languages:string[];
 timezone:string;default_currency:string;privacy_notice_version:string;telegram_operator_url:string;
 latin_name:string;quote_validity_days:number;quote_footer_note:string;visa_authorities:string[];supplier_desks:string[];two_factor_roles:string[]};
export type AIStatus={provider_ready:boolean;provider_approved:boolean;model:string;host:string;key_configured:boolean;assistants_allowed_in_this_environment:boolean};
export type Integrations={telegram:{mode:string;operator_link_configured:boolean};ai:AIStatus;whatsapp_outbound_approved:boolean;voice_processing_approved:boolean;patient_code_delivery:string;
 secure_document_storage:string;staff_two_factor_required:boolean;environment:string;managed_on_server:string[]};
export type OrganizationView={profile:Organization;editable:boolean;telegram_bot_owner?:boolean;integrations?:Integrations};

const TZ_KEY='medtour_tz',ORG_KEY='medtour_org';

export function rememberTimezone(zone:string){try{sessionStorage.setItem(TZ_KEY,zone);}catch{}}
export function rememberDisplay(p:{timezone:string;calendar:string;digits:string}){
 try{sessionStorage.setItem(TZ_KEY,p.timezone);sessionStorage.setItem('medtour_cal',p.calendar);sessionStorage.setItem('medtour_digits',p.digits);}catch{}
}
export function currentTimezone():string|undefined{
 if(typeof window==='undefined')return undefined;
 try{return sessionStorage.getItem(TZ_KEY)||undefined;}catch{return undefined;}
}
export function rememberOrganization(o:Organization){try{sessionStorage.setItem(ORG_KEY,JSON.stringify(o));}catch{}}
export function cachedOrganization():Organization|null{
 if(typeof window==='undefined')return null;
 try{const raw=sessionStorage.getItem(ORG_KEY);return raw?JSON.parse(raw) as Organization:null;}catch{return null;}
}

export async function loadOrganization():Promise<OrganizationView>{
 const view=await request<OrganizationView>('/organization/profile');
 rememberOrganization(view.profile);return view;
}
export async function loadProfile():Promise<Profile>{
 const p=await request<Profile>('/account/profile');rememberDisplay(p);return p;
}

export const LANGUAGE_NAMES:Record<string,string>={fa:'فارسی',ar:'العربية',en:'English',ps:'پښتو',prs:'دری'};
export const CURRENCIES=['USD','EUR','IRR','AED','TRY','IQD','AFN','GBP'];
export const TIMEZONES:[string,string][]=[
 ['Asia/Tehran','تهران (ایران)'],['Asia/Kabul','کابل (افغانستان)'],['Asia/Baghdad','بغداد (عراق)'],
 ['Asia/Dubai','دبی (امارات)'],['Asia/Karachi','کراچی (پاکستان)'],['Asia/Baku','باکو (آذربایجان)'],
 ['Europe/Istanbul','استانبول (ترکیه)'],['Asia/Riyadh','ریاض (عربستان)'],['Asia/Muscat','مسقط (عمان)'],
 ['Asia/Dushanbe','دوشنبه (تاجیکستان)'],['Europe/London','لندن'],['Europe/Berlin','برلین'],['UTC','زمان جهانی (UTC)'],
];

/** Pages a user may pick as the page opened after sign-in. */
export const START_PAGES:[string,string][]=[['','پیش‌فرض نقش من'],['dashboard','داشبورد'],['admin-center','مرکز کنترل مدیریتی'],['patients','بیماران'],['cases','پرونده‌ها'],['journey','مسیر بیمار'],['conversations','گفت‌وگوها'],['appointments','نوبت‌ها'],['quotations','پیش‌فاکتورها'],['visa','ویزای درمانی'],['accommodation','اقامت و هتل'],['travel-coordination','ترانسفر و مترجم'],['hospital-workspace','پرتال بیمارستان'],['physician-workspace','پرتال پزشک'],['doctor-cases','پرونده‌های پزشک'],['agent-portal','پرتال نماینده']];
export const MFA_ROLES:[string,string][]=[['admin','مدیر'],['operator','اپراتور'],['hospital','بیمارستان'],['physician','پزشک'],['doctor','پزشک بازبین'],['agent','نماینده'],['cms_editor','ویرایشگر محتوا']];
