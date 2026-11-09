const descriptions={
 de:['Reparatur, Verkauf und individueller Aufbau von MIG/MAG- und WIG/TIG-Schweißbrennern in Kleve. Beschreiben Sie den Fehler und senden Sie Boris Fotos Ihres Brenners.','Schweißbrenner verstehen: interaktive 3D-Bauteile, typische Fehlerbilder und Katalogreferenzen für MIG/MAG und WIG/TIG. Mit direkter Reparaturanfrage an Boris.'],
 en:['MIG/MAG and TIG welding torch repair, sales and individual assembly in Kleve, Germany. Describe the fault and send Boris photos of your torch.','Understand your welding torch: interactive 3D parts, common symptoms and catalogue references for MIG/MAG and TIG, with direct repair enquiries to Boris.'],
 nl:['Reparatie, verkoop en individuele samenstelling van MIG/MAG- en TIG-lastoortsen in Kleve. Beschrijf het probleem en stuur Boris foto’s van uw toorts.','Ontdek uw lastoorts: interactieve 3D-onderdelen, veelvoorkomende problemen en catalogusverwijzingen voor MIG/MAG en TIG. Vraag Boris direct om een reparatie.'],
 zh:['德国克莱沃的 MIG/MAG 和 TIG 焊枪维修、销售及按需组装服务。描述故障并向 Boris 发送焊枪照片。','通过交互式三维零件、常见故障现象和目录参考了解 MIG/MAG 和 TIG 焊枪，并直接向 Boris 提交维修咨询。'],
 pl:['Naprawa, sprzedaż i indywidualny montaż uchwytów MIG/MAG i TIG w Kleve. Opisz usterkę i wyślij Borisowi zdjęcia swojego uchwytu.','Poznaj uchwyt spawalniczy: interaktywne części 3D, typowe objawy i odnośniki do katalogów MIG/MAG i TIG. Wyślij zapytanie o naprawę do Borisa.'],
 bg:['Ремонт, продажба и индивидуално сглобяване на MIG/MAG и TIG горелки в Клеве. Опишете повредата и изпратете снимки на Борис.','Опознайте горелката: интерактивни 3D части, типични симптоми и каталожни препратки за MIG/MAG и TIG. Изпратете запитване за ремонт до Борис.']
};
export function updateMetadata(page,lang,title){
 const description=(descriptions[lang]||descriptions.de)[page==='parts'?1:0];
 document.title=title;
 for(const selector of ['meta[name="description"]','meta[property="og:description"]','meta[name="twitter:description"]'])document.querySelector(selector)?.setAttribute('content',description);
 for(const selector of ['meta[property="og:title"]','meta[name="twitter:title"]'])document.querySelector(selector)?.setAttribute('content',title);
 document.querySelector('meta[property="og:locale"]')?.setAttribute('content',({de:'de_DE',en:'en_GB',nl:'nl_NL',zh:'zh_CN',pl:'pl_PL',bg:'bg_BG'})[lang]||'de_DE');
}
