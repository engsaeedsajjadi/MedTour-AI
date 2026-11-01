'use client';
import {useCallback,useEffect,useState} from 'react';
import Shell from './Shell';
import IntakeConsentActions from './IntakeConsentActions';
import {Row,request} from '@/lib/api';
import {cell,fa,tone} from '@/lib/i18n';
export type InputField={name:string,label:string,type?:'text'|'number'|'select'|'datetime-local'|'password'|'email',options?:string[],required?:boolean};
export default function ResourcePage({title,path,fields,columns,note,intro,approveDraftQuotes=false,showIntakeConsent=false,selectPatient=false}:{title:string,path:string,fields:InputField[],columns:{key:string,label:string}[],note?:string,intro?:React.ReactNode,approveDraftQuotes?:boolean,showIntakeConsent?:boolean,selectPatient?:boolean}){
 const [patientChoices,setPatientChoices]=useState<Row[]>([]);
 const [items,setItems]=useState<Row[]>([]),[values,setValues]=useState<Record<string,string>>({}),[error,setError]=useState(''),[loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[showForm,setShowForm]=useState(false),[approvingId,setApprovingId]=useState('');
 const load=useCallback(()=>{setLoading(true);request<Row[]>(path).then(setItems).catch(e=>setError(e.message)).finally(()=>setLoading(false));},[path]);
 useEffect(load,[load]);
 useEffect(()=>{if(!selectPatient)return;request<Row[]>('/patients?limit=200').then(setPatientChoices).catch(e=>setError(e.message));},[selectPatient]);
 async function save(e:React.FormEvent){e.preventDefault();setSaving(true);setError('');try{const body:Row={};for(const f of fields){const v=values[f.name]||'';if(f.required&&!v)throw new Error('فیلد «'+f.label+'» ضروری است');body[f.name]=f.type==='number'?Number(v):f.type==='datetime-local'?new Date(v).toISOString():v;}
 await request(path,{method:'POST',body:JSON.stringify(body)});setValues({});setShowForm(false);load();}catch(e){setError((e as Error).message);}finally{setSaving(false);}}
 async function approveDraftQuote(id:string){
  if(!approveDraftQuotes||path!=='/quotes'||!id)return;
  if(!window.confirm('آیا پیش‌فاکتور آزمایشی را تأیید می‌کنید؟ برای موارد واقعی بررسی و تأیید قیمت توسط مسئول مجاز ضروری است.'))return;
  setApprovingId(id);setError('');
  try{await request('/quotes/'+encodeURIComponent(id)+'/approve',{method:'PATCH'});load();}
  catch(e){setError((e as Error).message)}
  finally{setApprovingId('');}
 }
 return <Shell title={title}><div className="summary"><div><strong>{items.length.toLocaleString('fa-IR')}</strong><small>رکورد در فهرست جاری</small></div><div className="summaryRight">اطلاعات به‌روز از پایگاه داده سازمان</div></div>{intro&&<div className="infoBanner">{intro}</div>}{note&&<div className="infoBanner">{note}</div>}{error&&<div role="alert" className="errorBox">{error}</div>}<section className="panel"><div className="panelHeader"><h2>فهرست {title}</h2><button className="button" onClick={()=>setShowForm(!showForm)}>{showForm?'بستن فرم':'+ ثبت جدید'}</button></div>{showForm&&<form className="formGrid" onSubmit={save}>{fields.map(f=><label key={f.name}>{f.label}{f.name==='patient_id'&&selectPatient?<select required={f.required} value={values[f.name]||''} onChange={e=>setValues({...values,[f.name]:e.target.value})}>
  <option value="">انتخاب بیمار ثبت‌شده</option>
  {patientChoices.map(p=><option key={String(p.id)} value={String(p.id)}>{String(p.full_name||'بیمار')} — {String(p.id).slice(0,8)}…</option>)}
 </select>:f.type==='select'?<select value={values[f.name]||''} onChange={e=>setValues({...values,[f.name]:e.target.value})}><option value="">انتخاب کنید</option>{f.options?.map(x=><option key={x} value={x}>{fa(x)}</option>)}</select>:<input required={f.required} type={f.type||'text'} autoComplete={f.type==='password'?'new-password':undefined} dir={f.type==='email'||f.type==='password'?'ltr':undefined} minLength={f.type==='password'?12:undefined} value={values[f.name]||''} onChange={e=>setValues({...values,[f.name]:e.target.value})}/>}</label>)}<div className="formActions"><button className="button" disabled={saving}>{saving?'در حال ذخیره…':'ثبت در پایگاه داده'}</button></div></form>}<div className="tableScroll"><table><thead><tr>{columns.map(c=><th key={c.key}>{c.label}</th>)}{approveDraftQuotes&&<th>عملیات</th>}</tr></thead><tbody>{loading?<tr><td colSpan={columns.length+(approveDraftQuotes?1:0)}>در حال دریافت اطلاعات…</td></tr>:items.length===0?<tr><td colSpan={columns.length+(approveDraftQuotes?1:0)} className="empty">هنوز موردی ثبت نشده است.</td></tr>:items.map((row,i)=><tr key={String(row.id||i)}>{columns.map(c=><td key={c.key}>{c.key==='id'||(c.key.endsWith('_id')&&typeof row[c.key]==='string'&&String(row[c.key]).length>20)?<code title={String(row[c.key]||'')}>{String(row[c.key]||'').slice(0,8)}…</code>:c.key==='status'||c.key==='role'?<span className={'badge '+tone(row[c.key])}>{fa(row[c.key])}</span>:cell(c.key,row[c.key])}</td>)}{approveDraftQuotes&&<td>{row.status==='draft'?<button type="button" className="button secondary" disabled={!!approvingId} onClick={()=>approveDraftQuote(String(row.id??''))}>{approvingId===String(row.id)?'در حال تأیید…':'تأیید پیش‌فاکتور'}</button>:'—'}</td>}</tr>)}</tbody></table></div></section>{showIntakeConsent&&<IntakeConsentActions patients={items}/>}</Shell>;
}
