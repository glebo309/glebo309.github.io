import test from 'node:test';
import assert from 'node:assert/strict';
import {copy, requestText, resolveLanguage} from './content.mjs';
test('all four languages have complete nonempty translations',()=>{
 assert.deepEqual(Object.keys(copy).sort(),['de','en','nl','zh']);
 for(const lang of Object.values(copy)){
  assert.deepEqual(Object.keys(lang).sort(),Object.keys(copy.de).sort());
  for(const value of Object.values(lang)) assert.ok(typeof value==='string' && value.trim().length);
 }
});
test('unknown language falls back safely',()=>{
 assert.equal(resolveLanguage('xx'),'de'); assert.equal(resolveLanguage('zh'),'zh');
});
test('request retains the customer details and selected service',()=>{
 const result=requestText('en',{service:'repair',process:'TIG',name:'M. Example',email:'m@example.com',message:'Gas leak at torch neck'});
 for(const text of ['Repair','TIG','M. Example','m@example.com','Gas leak at torch neck']) assert.ok(result.includes(text));
 assert.ok(!result.includes('undefined'));
});
