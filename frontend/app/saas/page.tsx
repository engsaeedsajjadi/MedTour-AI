'use client';

import {useCallback, useEffect, useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Plan = {code: string; limits: Record<string, number>};
type Usage = {
 plan_code: string | null;
 active: boolean;
 counts: Record<string, number>;
 limits: Record<string, number> | null;
 quota_enforcement: string[];
 billing_integrated: boolean;
};
type Subscription = {
 status: string;
 plan_code: string | null;
 active?: boolean;
 enforced: boolean;
};

const labels: Record<string, string> = {
 patients: 'بیماران', cases: 'پرونده‌ها', users: 'کاربران'
};

export default function SaaSPage() {
 const [plans, setPlans] = useState<Plan[]>([]);
 const [usage, setUsage] = useState<Usage | null>(null);
 const [subscription, setSubscription] = useState<Subscription | null>(null);
 const [error, setError] = useState('');
 const [busy, setBusy] = useState(false);
 const [loading, setLoading] = useState(true);

 const load = useCallback(async () => {
  setLoading(true);
  try {
   const [p, u, s] = await Promise.all([
    request<Plan[]>('/saas/plans'),
    request<Usage>('/saas/usage'),
    request<Subscription>('/saas/subscription')
   ]);
   setPlans(p); setUsage(u); setSubscription(s); setError('');
  } catch (e) {
   setError((e as Error).message);
  } finally { setLoading(false); }
 }, []);

 useEffect(() => { void load(); }, [load]);

 async function activateFree() {
  if (!window.confirm('پلن رایگان آزمایشی برای این سازمان فعال شود؟ این عملیات قابل تکرار نیست.')) return;
  setBusy(true); setError('');
  try {
   await request('/saas/subscription/activate-free', {method:'POST'});
   await load();
  } catch (e) {
   setError((e as Error).message);
  } finally { setBusy(false); }
 }

 return <Shell title="اشتراک و سهمیه سازمان">
  <div className="infoBanner">
   این بخش فقط کنترل فنی سهمیه است؛ قیمت‌گذاری تجاری، درگاه پرداخت، صدور صورتحساب و ارتقای پولی هنوز فعال نیستند.
   محیط فعلی برای تست مصنوعی است، نه بیماران واقعی.
  </div>
  {error && <div className="errorBox" role="alert">{error}</div>}
  {loading && <section className="panel">در حال دریافت وضعیت اشتراک…</section>}
  {!loading && <section className="panel">
   <div className="panelHeader"><h2>اشتراک فعلی</h2></div>
   <p>وضعیت: <strong>{subscription?.status || 'نامشخص'}</strong></p>
   <p>پلن: <strong>{subscription?.plan_code || 'ثبت نشده'}</strong></p>
   <p>کنترل سهمیه بیماران و پرونده‌ها: <strong>{usage?.quota_enforcement?.length ? 'فعال' : 'برای سازمان‌های قدیمیِ ثبت‌نشده، در محیط توسعه غیرفعال'}</strong></p>
   {subscription?.status === 'unprovisioned' && <button
     className="button" disabled={busy} onClick={()=>void activateFree()}>
     {busy ? 'در حال ثبت…' : 'فعال‌سازی یک‌باره پلن رایگان'}
   </button>}
  </section>}
  {!!usage && <section className="panel">
   <div className="panelHeader"><h2>مصرف منابع سازمان</h2></div>
   <div className="tableScroll"><table><thead><tr><th>منبع</th><th>مصرف واقعی</th><th>سقف پلن</th><th>وضعیت</th></tr></thead>
    <tbody>{Object.entries(usage.counts).map(([key, count])=>{
     const limit=usage.limits?.[key];
     return <tr key={key}><td>{labels[key] || key}</td><td>{count.toLocaleString('fa-IR')}</td>
      <td>{limit == null ? '—' : limit.toLocaleString('fa-IR')}</td>
      <td>{limit == null ? 'تعریف‌نشده' : count >= limit ? 'سقف تکمیل' : 'در محدوده'}</td>
     </tr>;
    })}</tbody></table></div>
   <div className="infoBanner">در این نسخه تنها ایجاد بیمار و پرونده کنترل سهمیه دارد؛ محدودیت کاربران هنوز به همه مسیرهای ایجاد حساب متصل نیست.</div>
  </section>}
  <section className="panel">
   <div className="panelHeader"><h2>پلن‌های فنی قابل تعریف</h2></div>
   <div className="tableScroll"><table><thead><tr><th>پلن</th><th>بیماران</th><th>پرونده‌ها</th><th>کاربران</th></tr></thead>
    <tbody>{plans.map(p=><tr key={p.code}>
     <td>{p.code}</td>
     <td>{p.limits.patients?.toLocaleString('fa-IR')}</td>
     <td>{p.limits.cases?.toLocaleString('fa-IR')}</td>
     <td>{p.limits.users?.toLocaleString('fa-IR')}</td>
    </tr>)}</tbody></table></div>
  </section>
 </Shell>;
}
