/** Personal and organization settings shared by the panel. Cached per browser tab only. */
import {request} from './api';

export type Session={started_at:string;last_used_at:string;expires_at:string;two_factor:boolean};
export type Profile={email:string;role:string;organization_slug:string;display_name:string;timezone:string;
 two_factor_enabled:boolean;two_factor_required:boolean;sessions:Session[]};
export type Organization={display_name:string;contact_email:string;contact_phone:string;website:string;
 privacy_notice_url:string;patient_support_hours:string;default_language:string;enabled_languages:string[];
 timezone:string;default_currency:string};
export type Integrations={telegram:{mode:string;operator_link_configured:boolean};patient_code_delivery:string;
 secure_document_storage:string;staff_two_factor_required:boolean;environment:string;managed_on_server:string[]};
export type OrganizationView={profile:Organization;editable:boolean;integrations?:Integrations};

const TZ_KEY='medtour_tz',ORG_KEY='medtour_org';

export function rememberTimezone(zone:string){try{sessionStorage.setItem(TZ_KEY,zone);}catch{}}
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
 const p=await request<Profile>('/account/profile');rememberTimezone(p.timezone);return p;
}

export const LANGUAGE_NAMES:Record<string,string>={fa:'فارسی',ar:'العربية',en:'English',ps:'پښتو',prs:'دری'};
export const CURRENCIES=['USD','EUR','IRR','AED','TRY','IQD','AFN','GBP'];
export const TIMEZONES:[string,string][]=[
 ['Asia/Tehran','تهران (ایران)'],['Asia/Kabul','کابل (افغانستان)'],['Asia/Baghdad','بغداد (عراق)'],
 ['Asia/Dubai','دبی (امارات)'],['Asia/Karachi','کراچی (پاکستان)'],['Asia/Baku','باکو (آذربایجان)'],
 ['Europe/Istanbul','استانبول (ترکیه)'],['Asia/Riyadh','ریاض (عربستان)'],['Asia/Muscat','مسقط (عمان)'],
 ['Asia/Dushanbe','دوشنبه (تاجیکستان)'],['Europe/London','لندن'],['Europe/Berlin','برلین'],['UTC','زمان جهانی (UTC)'],
];
