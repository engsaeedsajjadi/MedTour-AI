import type {MetadataRoute} from 'next';
export default function robots():MetadataRoute.Robots {
 return {rules:[
  {userAgent:'*',allow:'/public/',disallow:[
   '/login','/dashboard','/patients','/patient-portal','/agent-portal',
   '/cases','/cms','/finance','/settings','/secure-documents','/staff',
   '/conversations','/messaging','/reports','/admin-center','/intake-',
   '/consent','/appointments','/operations','/knowledge','/quotations',
  ]}
 ]};
}
