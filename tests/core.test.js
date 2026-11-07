const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const C = require('../extension/core.js');
const ext=path.join(__dirname,'../extension');
test('manifest is a valid MV3 extension, with all referenced assets',()=>{
 const m=JSON.parse(fs.readFileSync(path.join(ext,'manifest.json')));
 assert.equal(m.manifest_version,3);
 for(const f of [m.background.service_worker,m.options_ui.page,...Object.values(m.icons),...m.content_scripts.flatMap(x=>x.js)]) assert.ok(fs.existsSync(path.join(ext,f)),`missing ${f}`);
});
test('YouTube json3 subtitles parse correctly',()=>{
 const cues=C.parseYoutubeJson3({events:[{tStartMs:1250,segs:[{utf8:'你好'},{utf8:'，世界'}]},{tStartMs:5500,segs:[{utf8:'数字是 123'}]}]});
 assert.equal(cues.length,2);assert.equal(cues[0].time,1.25);assert.equal(cues[0].text,'你好，世界');
});
test('Bilibili subtitle format is parsed',()=>{
 const cues=C.parseBiliJson({body:[{from:4.5,to:7,content:'测试字幕 A'},{from:8.1,to:9,content:'测试字幕 B'}]});
 assert.equal(cues.length,2);assert.equal(cues[1].time,8.1);
});
test('SRT and VTT imports contain timestamps',()=>{
 const srt='1\n00:00:01,250 --> 00:00:04,000\n第一个概念\n\n2\n00:00:06,100 --> 00:00:07,300\n第二个概念\n';
 assert.equal(C.parseSrtVtt(srt).length,2);
 assert.equal(C.parseSrtVtt(srt)[0].time,1.25);
 const vtt='WEBVTT\n\n00:01.100 --> 00:04.000\nHello World\n\n00:05.000 --> 00:07.000\nNext Chapter';
 assert.equal(C.parseSrtVtt(vtt).length,2);
});
test('identical subtitle within 5s deduplicates; distant replay does not',()=>{
 const cues=C.mergeCues([{time:10,text:'量子力学概论',source:'platform'}], [{time:12,text:'量子力学概论',source:'cc'},{time:400,text:'量子力学概论',source:'cc'}]);
 assert.equal(cues.length,2);assert.equal(cues[1].time,400);
});
test('offline markdown has source-linked timecodes and full appendix',()=>{
 const s={title:'知识测试',url:'https://www.youtube.com/watch?v=xYz',createdAt:'2026-11-06T00:00:00Z',segments:[{time:62,text:'我们首先定义实验条件',source:'import'},{time:80,text:'因为实验成功所以出现了结论',source:'import'}]};
 const md=C.buildDocumentMarkdown(s);
 assert.ok(md.includes('## 全部已收集文本'));
 assert.ok(md.includes('我们首先定义实验条件'));
 assert.ok(md.includes('[01:02](https://www.youtube.com/watch?v=xYz&t=62s)'));
});
test('exported HTML escapes unsafe caption script tags',()=>{
 const s={title:'<script>alert(1)</script>',url:'https://www.bilibili.com/video/BV1234567890',segments:[{time:0,text:'<img src=x onerror=alert(2)>',source:'import'}]};
 const html=C.buildHtmlDocument(s);
 assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
 assert.ok(!html.includes('<img src=x'));
 assert.ok(!html.includes('onerror=alert(2)')); // subtitle markup is stripped before exporting
});
test('URL query params in hyperlinks are not double-escaped',()=>{
 const html=C.markdownToSafeHtml('- [01:02](https://www.youtube.com/watch?v=abc&t=62s) test');
 assert.ok(html.includes('href="https://www.youtube.com/watch?v=abc&amp;t=62s"'));
 assert.ok(!html.includes('&amp;amp;'));
});
test('unsafe local filenames are sanitized',()=>{
 assert.equal(C.makeFilename('a/b:c*?<>|','html'),'a_b_c______知识笔记.html');
});
test('local markdown states excerpt nature, not fabricated AI research',()=>{
 const d=C.buildLocalMarkdown([{time:0,text:'这是关于星系天体物理的讲解'},{time:60,text:'银河系的主要结构包括旋臂'},{time:100,text:'关于星系的另一段描述'}],{url:'https://www.youtube.com/watch?v=x'});
 assert.ok(d.includes('本地规则提取'));assert.ok(d.includes('字幕原话'));assert.ok(d.includes('片段'));
});
