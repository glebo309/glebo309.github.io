import {parts} from './teile/data.mjs';
export const symptoms=[
 {id:'mig-feed',family:'mig',partIds:['mig-liner','mig-tip']},
 {id:'mig-heat',family:'mig',partIds:['mig-neck','mig-diffuser','mig-cable']},
 {id:'mig-gas',family:'mig',partIds:['mig-nozzle','mig-diffuser','mig-cable']},
 {id:'mig-trigger',family:'mig',partIds:['mig-trigger','mig-cable']},
 {id:'tig-cup',family:'tig',partIds:['tig-cup','tig-insulator']},
 {id:'tig-clamp',family:'tig',partIds:['tig-collet','tig-body','tig-backcap']},
 {id:'tig-gas',family:'tig',partIds:['tig-backcap','tig-insulator','tig-cup']},
 {id:'tig-heat',family:'tig',partIds:['tig-body','tig-collet','tig-hoses']}
];
const keys=['tag','title','intro','process','possible','note','view','enquire','clear','selected','remove','mig-feed','mig-heat','mig-gas','mig-trigger','tig-cup','tig-clamp','tig-gas','tig-heat'];
const values={
 de:['PROBLEM BESCHREIBEN','Was stimmt mit Ihrem Brenner nicht?','Wählen Sie Ihr Verfahren und das passende Fehlerbild. So finden Sie mögliche Bauteile und können Boris gezielt anfragen.','Schweißverfahren','Diese Bauteile können eine Rolle spielen','Eine erste Orientierung, keine Diagnose. Auch Gerät, Einstellungen und Gasversorgung können die Ursache sein. Boris beurteilt den konkreten Fall.','In 3D ansehen','Mit diesem Fehlerbild anfragen','Auswahl zurücksetzen','Beschriebenes Fehlerbild','Fehlerbild entfernen','Draht läuft ungleichmäßig','Brenner wird ungewöhnlich heiß','Gasabdeckung unzureichend / Poren','Keine Reaktion auf den Taster','Keramikdüse gerissen / gebrochen','Wolframelektrode sitzt nicht fest','Gasabdeckung unzureichend / Poren','Brenner wird ungewöhnlich heiß'],
 en:['DESCRIBE THE PROBLEM','What is wrong with your torch?','Choose your welding process and the symptom. Explore potentially relevant parts and send Boris a focused enquiry.','Welding process','Parts that may be involved','Initial guidance, not a diagnosis. The machine, settings and gas supply can also be responsible. Boris will assess your specific case.','Explore in 3D','Enquire about this symptom','Clear selection','Reported symptom','Remove symptom','Uneven wire feeding','Torch gets unusually hot','Poor gas coverage / porosity','Trigger does not respond','Ceramic cup cracked / broken','Tungsten electrode is loose','Poor gas coverage / porosity','Torch gets unusually hot'],
 nl:['BESCHRIJF HET PROBLEEM','Wat is er mis met uw lastoorts?','Kies uw lasproces en het probleem. Bekijk mogelijk betrokken onderdelen en stuur Boris een gerichte aanvraag.','Lasproces','Deze onderdelen kunnen een rol spelen','Een eerste indicatie, geen diagnose. Ook de machine, instellingen en gastoevoer kunnen de oorzaak zijn. Boris beoordeelt uw specifieke situatie.','Bekijk in 3D','Aanvraag over dit probleem','Selectie wissen','Beschreven probleem','Probleem verwijderen','Onregelmatige draadaanvoer','Lastoorts wordt ongewoon heet','Onvoldoende gasbescherming / poriën','Geen reactie op de schakelaar','Keramisch mondstuk gebarsten / gebroken','Wolfraamelektrode zit los','Onvoldoende gasbescherming / poriën','Lastoorts wordt ongewoon heet'],
 zh:['描述问题','您的焊枪出了什么问题？','请选择焊接工艺和故障现象，查看可能涉及的部件，并向 Boris 提交咨询。','焊接工艺','可能涉及的部件','仅供初步参考，并非故障诊断。焊机、设置和供气也可能是原因。Boris 将评估具体情况。','查看三维模型','就此问题咨询','清除选择','描述的故障现象','移除故障现象','送丝不均匀','焊枪异常发热','气体保护不足 / 气孔','按下开关无反应','陶瓷喷嘴开裂 / 破损','钨极夹持不牢','气体保护不足 / 气孔','焊枪异常发热'],
 pl:['OPISZ PROBLEM','Co dzieje się z Twoim uchwytem?','Wybierz metodę spawania i objaw. Zobacz części, które mogą mieć znaczenie, i wyślij Borisowi konkretne zapytanie.','Metoda spawania','Te części mogą mieć znaczenie','Wstępna wskazówka, nie diagnoza. Przyczyną mogą być też urządzenie, ustawienia i dopływ gazu. Boris oceni konkretny przypadek.','Obejrzyj w 3D','Zapytaj o ten problem','Wyczyść wybór','Opisany objaw','Usuń objaw','Nierównomierne podawanie drutu','Uchwyt nadmiernie się nagrzewa','Niewystarczająca osłona gazowa / pory','Brak reakcji na przycisk','Pęknięta / uszkodzona dysza ceramiczna','Elektroda wolframowa jest luźna','Niewystarczająca osłona gazowa / pory','Uchwyt nadmiernie się nagrzewa'],
 bg:['ОПИШЕТЕ ПРОБЛЕМА','Какъв е проблемът с горелката?','Изберете процеса на заваряване и симптома. Разгледайте възможните засегнати части и изпратете конкретно запитване до Борис.','Процес на заваряване','Тези части може да имат отношение','Първоначална насока, а не диагноза. Причината може да е и в машината, настройките или подаването на газ. Борис ще прецени конкретния случай.','Разгледайте в 3D','Запитване за този проблем','Изчистете избора','Описан симптом','Премахнете симптома','Неравномерно подаване на тел','Горелката се нагрява необичайно','Недостатъчна газова защита / пори','Няма реакция при натискане на бутона','Напукана / счупена керамична дюза','Волфрамовият електрод е хлабав','Недостатъчна газова защита / пори','Горелката се нагрява необичайно']
};
export const symptomCopy=Object.fromEntries(Object.entries(values).map(([lang,v])=>[lang,Object.fromEntries(keys.map((k,i)=>[k,v[i]]))]));
export function selectedSymptom(search,lang='de'){
 const s=symptoms.find(s=>s.id===new URLSearchParams(search).get('symptom'));
 return s?{...s,label:(symptomCopy[lang]||symptomCopy.de)[s.id]}:null;
}
export function symptomEnquiryURL(id,lang='de',part=''){
 const query=new URLSearchParams({lang:symptomCopy[lang]?lang:'de'});
 const symptom=symptoms.find(s=>s.id===id);
 if(symptom){query.set('symptom',id);if(symptom.partIds.includes(part))query.set('part',part);}
 return `../?${query}#contact`;
}

export function symptomSelectionQuery(search,id){
 const query=new URLSearchParams(search),symptom=symptoms.find(s=>s.id===id),part=parts.find(p=>p.id===query.get('part'));
 if(symptom){query.set('symptom',symptom.id);if(part&&part.family!==symptom.family)query.delete('part');}
 else query.delete('symptom');
 return query;
}
