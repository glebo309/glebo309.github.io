import test from 'node:test';
import assert from 'node:assert/strict';
import {copy, requestText, resolveLanguage} from './content.mjs';
test('all six languages have complete nonempty translations',()=>{
 assert.deepEqual(Object.keys(copy).sort(),['bg','de','en','nl','pl','zh']);
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
test('technical request preserves machine, torch model, cooling and cable length in every language',()=>{
 for(const lang of Object.keys(copy)){
  const result=requestText(lang,{service:'sales',process:'TIG',name:'Example',email:'test@example.com',message:'Replacement torch',machine:'Machine X',torchModel:'Torch Y',cooling:'water',cableLength:'5 m'});
  for(const text of ['Machine X','Torch Y','5 m',copy[lang].water]) assert.ok(result.includes(text),`${lang}: missing ${text}`);
  assert.ok(!result.includes('undefined'));
 }
});
test('unknown technical selections use the localized not-sure label',()=>{
 const result=requestText('de',{service:'repair',process:'MIG/MAG',name:'Example',email:'test@example.com',message:'Repair',cooling:'?'});
 assert.ok(result.includes(copy.de.coolingLabel+': '+copy.de.other));
 assert.ok(!result.includes('undefined'));
});
