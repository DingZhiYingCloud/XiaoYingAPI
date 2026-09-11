/*! For license information please see 12870.fb96aa35.js.LICENSE.txt */
!function(e,n){"object"==typeof module&&"object"==typeof module.exports?n():"function"==typeof define&&define.amd?define([],n):(e="undefined"!=typeof globalThis?globalThis:e||self)&&n()}(this,function(){"use strict";"object"==typeof window&&(window.openRedirect={version:"1.2.20",webpackPluginVersion:"3.4.22",reportOnly:!1})}),!function(e,n){"object"==typeof exports&&"undefined"!=typeof module?n(exports):"function"==typeof define&&define.amd?define(["exports"],n):n((e="undefined"!=typeof globalThis?globalThis:e||self).xss={})}(this,function(e){"use strict";var n=function(){return(n=Object.assign||function(e){for(var n,o=1,a=arguments.length;o<a;o++)for(var t in n=arguments[o])Object.prototype.hasOwnProperty.call(n,t)&&(e[t]=n[t]);return e}).apply(this,arguments)};function o(e,n,o){if(o||2==arguments.length)for(var a,t=0,r=n.length;t<r;t++)!a&&t in n||(a||(a=Array.prototype.slice.call(n,0,t)),a[t]=n[t]);return e.concat(a||Array.prototype.slice.call(n))}var a=/[^a-zA-Z0-9\\_:.-]/gim,t=/</g,r=/>/g,i=/&#([a-zA-Z0-9]*);?/gim,d=/&quot;/g,s=/&colon;?/gim,R=/&newline;?/gim,l=/((j\s*a\s*v\s*a|v\s*b|l\s*i\s*v\s*e)\s*s\s*c\s*r\s*i\s*p\s*t\s*|m\s*o\s*c\s*h\s*a):/gi,c=/u\s*r\s*l\s*\(.*/gi,u=/e\s*x\s*p\s*r\s*e\s*s\s*s\s*i\s*o\s*n\s*\(.*/gi,h=/"/g,p=function(e){return e.replace(t,"&lt;").replace(r,"&gt;")},f={indexOf:function(e,n){var o,a;for(o=0,a=e.length;o<a;o++)if(e[o]===n)return o;return -1},forEach:function(e,n,o){var a,t;for(a=0,t=e.length;a<t;a++)n.call(o,e[a],a,e)},some:function(e,n,o){var a,t;for(a=0,t=e.length;a<t;a++)if(n.call(o,e[a],a,e))return!0;return!1},trim:function(e){return e.replace(/(^\s*)|(\s*$)/g,"")},includes:function(e,n){if("string"==typeof e)return -1!==e.indexOf(n);for(var o=0;o<e.length;o++)if(e[o]===n)return!0;return!1},spaceIndex:function(e){var n=/\s|\n|\t/.exec(e);return n?n.index:-1},uniq:function(e){for(var n={},o=[],a=0;a<e.length;a++)n[e[a]]||(o.push(e[a]),n[e[a]]=!0);return o},from:function(e){for(var n=[],o=0;o<e.length;o++)n.push(e[o]);return n},keys:function(e){var n=[];for(var o in e)n.push(o);return n}};function M(e){return null==e}function D(e){var n;return'"'===(n=e)[0]&&'"'===n[n.length-1]||"'"===n[0]&&"'"===n[n.length-1]?e.substr(1,e.length-2):e}function g(e){var n,o,a,t,r,i,d,s="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=",R="",l=0;for(e=function(e){e=e.replace(/rn/g,"n");for(var n="",o=0;o<e.length;o++){var a=e.charCodeAt(o);a<128?n+=String.fromCharCode(a):a>127&&a<2048?n+=String.fromCharCode(a>>6|192)+String.fromCharCode(63&a|128):n+=String.fromCharCode(a>>12|224)+String.fromCharCode(a>>6&63|128)+String.fromCharCode(63&a|128)}return n}(e);l<e.length;)t=(n=e.charCodeAt(l++))>>2,r=(3&n)<<4|(o=e.charCodeAt(l++))>>4,i=(15&o)<<2|(a=e.charCodeAt(l++))>>6,d=63&a,isNaN(o)?i=d=64:isNaN(a)&&(d=64),R=R+s.charAt(t)+s.charAt(r)+s.charAt(i)+s.charAt(d);return R}function H(e){var n,o,a,t,r,i,d="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=",s="",R=0;for(e=e.replace(/[^A-Za-z0-9+/=]/g,"");R<e.length;)n=d.indexOf(e.charAt(R++))<<2|(t=d.indexOf(e.charAt(R++)))>>4,o=(15&t)<<4|(r=d.indexOf(e.charAt(R++)))>>2,a=(3&r)<<6|(i=d.indexOf(e.charAt(R++))),s+=String.fromCharCode(n),64!==r&&(s+=String.fromCharCode(o)),64!==i&&(s+=String.fromCharCode(a));return function(e){for(var n="",o=0,a=0,t=0,r=0;o<e.length;)(a=e.charCodeAt(o))<128?(n+=String.fromCharCode(a),o++):a>191&&a<224?(n+=String.fromCharCode((31&a)<<6|63&(r=e.charCodeAt(o+1))),o+=2):(r=e.charCodeAt(o+1),n+=String.fromCharCode((15&a)<<12|(63&r)<<6|63&(t=e.charCodeAt(o+2))),o+=3);return n}(s)}function m(e,n,o){var a="",t=0,r=!1,i=!1,d=0,s=e.length,R="",l="";e:for(d=0;d<s;d++){var c=e.charAt(d);if(!1===r){if("<"===c){r=d;continue}}else if(!1===i){if("<"===c){a+=o(e.slice(t,d)),r=d,t=d;continue}if(">"===c||d===s-1){a+=o(e.slice(t,r)),R=function(e){var n,o=f.spaceIndex(e);return n=-1===o?e.slice(1,-1):e.slice(1,o+1),"/"===(n=f.trim(n).toLowerCase()).slice(0,1)&&(n=n.slice(1)),"/"===n.slice(-1)&&(n=n.slice(0,-1)),n}(l=e.slice(r,d+1)),a+=n(r,a.length,R,l,"</"===l.slice(0,2)),t=d+1,r=!1;continue}if('"'===c||"'"===c)for(var u=1,h=e.charAt(d-u);""===h.trim()||"="===h;){if("="===h){i=c;continue e}h=e.charAt(d-++u)}}else if(c===i){i=!1;continue}}return t<s&&(a+=o(e.substr(t))),a}function X(e,n){var o=0,t=0,r=[],i=!1,d=e.length;function s(e,o){if(!((e=(e=f.trim(e)).replace(a,"").toLowerCase()).length<1)){var t=n(e,o||"");t&&r.push(t)}}for(var R=0;R<d;R++){var l=e.charAt(R),c=void 0;if(!1!==i||"="!==l){if(!1===i||R!==t){if(/\s|\n|\t/.test(l)){if(e=e.replace(/\s|\n|\t/g," "),!1===i){if(-1===(c=function(e,n){for(;n<e.length;n++){var o=e[n];if(" "!==o)return"="===o?n:-1}return -1}(e,R))){s(f.trim(e.slice(o,R))),i=!1,o=R+1;continue}R=c-1;continue}if(-1===(c=function(e,n){for(;n>0;n--){var o=e[n];if(" "!==o)return"="===o?n:-1}return -1}(e,R-1))){s(i,D(f.trim(e.slice(o,R)))),i=!1,o=R+1;continue}}}else{if(-1===(c=e.indexOf(l,R+1)))break;s(i,f.trim(e.slice(t+1,c))),i=!1,o=(R=c)+1}}else i=e.slice(o,R),o=R+1,t='"'===e.charAt(o)||"'"===e.charAt(o)?o:function(e,n){for(;n<e.length;n++){var o=e[n];if(" "!==o)return"'"===o||'"'===o?n:-1}return -1}(e,R+1)}return o<e.length&&(!1===i?s(e.slice(o)):s(i,D(f.trim(e.slice(o))))),f.trim(r.join(" "))}function v(e,n,o){if(o=function(e){return e=function(e){for(var n="",o=0,a=e.length;o<a;o++)n+=32>e.charCodeAt(o)?" ":e.charAt(o);return f.trim(n)}(e=(e=(e=e.replace(d,'"')).replace(i,function(e,n){return"x"===n[0]||"X"===n[0]?String.fromCharCode(parseInt(n.substr(1),16)):String.fromCharCode(parseInt(n,10))})).replace(s,":").replace(R," "))}(o),"href"===n||"src"===n){if("#"===(o=f.trim(o)))return"#";if("http://"!==o.substr(0,7)&&"https://"!==o.substr(0,8)&&"mailto:"!==o.substr(0,7)&&"tel:"!==o.substr(0,4)&&"data:image/"!==o.substr(0,11)&&"ftp://"!==o.substr(0,6)&&"./"!==o.substr(0,2)&&"../"!==o.substr(0,3)&&"#"!==o[0]&&"/"!==o[0])return""}else if("background"===n){if(l.lastIndex=0,l.test(o))return""}else if("style"===n&&(u.lastIndex=0,u.test(o)||(c.lastIndex=0,c.test(o)&&(l.lastIndex=0,l.test(o)))))return"";return o=function(e){return e=p(e=e.replace(h,"&quot;"))}(o)}var T=function(e){return"string"==typeof e?e.replace(/'/g,'"').replace('=""',"").replace(/\s+/g,"").toLowerCase():""},S=function(){function e(e){var n=function(e){var n={};for(var o in e)n[o]=e[o];return n}(e||{});n.stripIgnoreTag&&(n.onIgnoreTag,n.onIgnoreTag=function(){return""}),n.whiteList={},n.onTag=function(){},n.onTagAttr=function(){},n.onIgnoreTag=function(){},n.onIgnoreTagAttr=function(){},n.safeAttrValue=v,n.escapeHtml=p,this.options=Object.assign(n,e)}return e.prototype.process=function(e){if(!(e=(e=e||"").toString()))return"";var n,o,a,t,r,i,d=this.options,s=d.whiteList,R=d.onTag,l=d.onIgnoreTag,c=d.onTagAttr,u=d.onIgnoreTagAttr,h=d.safeAttrValue,p=d.escapeHtml;d.stripBlankChar&&(e=(n=(n=e.split("")).filter(function(e){var n=e.charCodeAt(0);return!(127===n||n<=31&&10!==n&&13!==n)})).join("")),d.allowCommentTag||(e=function(e){for(var n="",o=0;o<e.length;){var a=e.indexOf("\x3c!--",o);if(-1===a){n+=e.slice(o);break}n+=e.slice(o,a);var t=e.indexOf("--\x3e",a);if(-1===t)break;o=t+3}return n}(e));var M=!1;d.stripIgnoreTagBody&&(o=d.stripIgnoreTagBody,"function"!=typeof(a=l)&&(a=function(){}),t=!Array.isArray(o),r=[],i=!1,l=(M={onIgnoreTag:function(e,n,d){var s;if(s=e,t||-1!==f.indexOf(o,s)){if(d.isClosing){var R="[/removed]",l=d.position+R.length;return r.push([!1!==i?i:d.position,l]),i=!1,R}return i||(i=d.position),"[removed]"}return a(e,n,d)},remove:function(e){var n="",o=0;return f.forEach(r,function(a){n+=e.slice(o,a[0]),o=a[1]}),n+=e.slice(o)}}).onIgnoreTag);var D=m(e,function(e,n,o,a,t){var r={sourcePosition:e,position:n,isClosing:t,isWhite:Object.prototype.hasOwnProperty.call(s,o)},i=R(o,a,r);if(null!=i)return i;if(r.isWhite){if(r.isClosing)return"</".concat(o,">");var d=function(e){var n=f.spaceIndex(e);if(-1===n)return{html:"",closing:"/"===e[e.length-2]};var o="/"===(e=f.trim(e.slice(n+1,-1)))[e.length-1];return o&&(e=f.trim(e.slice(0,-1))),{html:e,closing:o}}(a),M=s[o],D=X(d.html,function(e,n){var a=-1!==f.indexOf(M,e),t=c(o,e,n,a);return null==t?a?(n=h(o,e,n,null))?"".concat(e,'="').concat(n,'"'):e:null==(t=u(o,e,n,a))?void 0:t:t});return a="<".concat(o),D&&(a+=" ".concat(D)),d.closing&&(a+=" /"),a+=">"}return null==(i=l(o,a,r))?p(a):i},p);return M&&(D=M.remove(D)),D},e}(),b=Function("\nvar _checkXSS = function (it) {\n  return it && it.Math == Math && it;\n};\nreturn _checkXSS(typeof globalThis === 'object' && globalThis) ||\n_checkXSS(typeof window === 'object' && window) ||\n_checkXSS(typeof self === 'object' && self) ||\n_checkXSS(typeof global === 'object' && global) ||\nFunction('return this')();\n")(),y=new(function(){function e(){var e=this;this.batchData=[],this.uniqKeys=new Set,this.timeout=2e3,this.lock=!1,this.getSlardarBid=function(){var n,o,a="douyin_web";if(!f.includes(a,"bid"))return a;if(e.config&&e.config.bid)return e.config.bid;if(b&&b._xssBid)return b._xssBid;if(b&&b.slardar&&"function"==typeof b.slardar.config){var t=(b.slardar.config()||{}).bid;if(t)return t}if(b&&b.Slardar&&"function"==typeof b.Slardar.config){var r=(b.Slardar.config()||{}).bid;if(r)return r}return(null===(o=null===(n=null==b?void 0:b.Slardar)||void 0===n?void 0:n._baseParams)||void 0===o?void 0:o.bid)||"argus"},this.getConfigRegion=function(){var n;return f.includes("cn","region")?e.config&&e.config.region?e.config.region:((null===(n=null==b?void 0:b.gfdatav1)||void 0===n?void 0:n.region)||"cn").toLowerCase():"cn"},this.gerReportUrl=function(){var n={cn:H("aHR0cHM6Ly9tb24uemlqaWVhcGkuY29tL21vbml0b3JfYnJvd3Nlci9jb2xsZWN0L2JhdGNoL3NlY3VyaXR5Lz9iaWQ9"),boe:H("aHR0cHM6Ly9tb24uemlqaWVhcGkuY29tL21vbml0b3JfYnJvd3Nlci9jb2xsZWN0L2JhdGNoL3NlY3VyaXR5Lz9iaWQ9"),ttp:H("aHR0cHM6Ly9tb24udXMudGlrdG9rdi5jb20vbW9uaXRvcl9icm93c2VyL2NvbGxlY3QvYmF0Y2gvc2VjdXJpdHkvP2JpZD0="),va:H("aHR0cHM6Ly9tb24tdmEuYnl0ZW92ZXJzZWEuY29tL21vbml0b3JfYnJvd3Nlci9jb2xsZWN0L2JhdGNoL3NlY3VyaXR5Lz9iaWQ9"),maliva:H("aHR0cHM6Ly9tb24tdmEuYnl0ZW92ZXJzZWEuY29tL21vbml0b3JfYnJvd3Nlci9jb2xsZWN0L2JhdGNoL3NlY3VyaXR5Lz9iaWQ9"),sg:H("aHR0cHM6Ly9tb24tdmEuYnl0ZW92ZXJzZWEuY29tL21vbml0b3JfYnJvd3Nlci9jb2xsZWN0L2JhdGNoL3NlY3VyaXR5Lz9iaWQ9"),boei18n:H("aHR0cHM6Ly9tb24tdmEuYnl0ZW92ZXJzZWEuY29tL21vbml0b3JfYnJvd3Nlci9jb2xsZWN0L2JhdGNoL3NlY3VyaXR5Lz9iaWQ9")}[e.getConfigRegion()];if(n)return n+e.getSlardarBid()}}return e.prototype.setConfig=function(e){this.config=e},e.prototype.upload=function(){var e=this,n=this.gerReportUrl();!this.lock&&n&&0!==this.batchData.length&&(this.lock=!0,setTimeout(function(){var o=e.batchData.slice(0,100);e.batchData=e.batchData.slice(100),b.fetch(n,{method:"post",body:JSON.stringify(o),headers:{"Content-Type":"application/json"}}).catch(function(e){}),e.lock=!1,e.upload()},this.timeout))},e.prototype.generateKey=function(e){return e.collectKey?[e.collectMode,e.collectKey].join("___"):""},e.prototype.push=function(e){this.batchData.push(e),this.upload()},e.prototype.report=function(e){var n=this.generateKey(e);if(b.fetch&&e.collectKey){var o="object"==typeof window?window.location.href:"SSR";e.documentUrl=o;var a={age:Math.floor(Date.now()),type:"xss",url:o,body:e,"user-agent":""};"enforce"===e.disposition&&"SSR"!==o||(a.url=n),"SSR"===o&&(a.url="SSR___".concat(a.url),a.body.ssr=!0),this.push(a)}},e}()),G=function(e){for(var n=0,o=function(o){Array.isArray(e[o])?0===e[o].length?delete e[o]:(e[o]=f.from(f.uniq(e[o])),n+=e[o].length):0===f.keys(e[o]).length?delete e[o]:f.keys(e[o]).forEach(function(a){e[o][a]=f.from(f.uniq(e[o][a])),n+=e[o][a].length})},a=0,t=f.keys(e);a<t.length;a++)o(t[a]);return{count:n,ret:e}};function P(e,n){return y.setConfig(n),new S(n).process(e)}function A(e){var n,o=(n=/\s|\n|\t/.exec(e))?n.index:-1;if(-1===o)return{html:"",closing:"/"===e[e.length-2]};var a="/"===(e=e.slice(o+1,-1).trim())[e.length-1];return a&&(e=e.slice(0,-1).trim()),{html:e,closing:a}}var x=function(e){return -1===(e=(e=(e=(e=e.replace(/&colon;/gi,":")).replace(/&tab;/gi,"")).replace(/&newline;/gi,"")).replace(/(\t|\n|\r)/g,"")).indexOf("&#")?e.trim().toLowerCase():e.trim().replace(/&#(?:(x)([0-9a-f]+)|([0-9]+));?/gi,function(e,n,o,a){return String.fromCharCode(n?parseInt(o,16):parseInt(a))}).replace(/(\t|\n|\r)/g,"").toLowerCase()};function E(e,n){if(void 0===e&&(e=""),"string"!=typeof e)return!0;if(e=x(e),f.includes(e,"base64")&&!function(e){if(""===e||""===e.trim())return!0;try{return!f.includes(e,"data:text/html;base64")}catch(e){return!0}}(e))return n&&n("data:text/html;base64"),!1;var o=["expression(","behavior:","view-source:"];if(f.some(o,function(n){return -1!==e.indexOf(n)}))return f.forEach(o,function(o){-1!==e.indexOf(o)&&n&&n(o)}),!1;var a=["data:application","data:javascript","data:text/html","data:texthtml"];if(f.some(a,function(n){return -1!==e.indexOf(n)}))return f.forEach(a,function(o){-1!==e.indexOf(o)&&n&&n(o)}),!1;if(e.indexOf("javascript:")>0)return n&&n("javascript:"),!1;if(/^javascript:/i.test(e)){var t=e.slice(11).replace(/\s/g,"").trim();return!!f.some(["void","void(0)","void0","false","undefined",";"],function(e){return e===t})||(n&&n("javascript:"),!1)}return!0}var F=function(e,n){var o,a,t="<%= isSaveValidUrl =>";if("string"!=typeof e||(a=Number("<%= urlLimit =>"),void 0!==o&&(a=o),"NaN"!==e.toString()&&-1!==a&&e.length>=a)||E(e,n))return e;try{if(!0===(t=JSON.parse(t))||"true"===t){var r=new URL(e);return r.origin+r.pathname}}catch(e){}return"#"};function w(e,n,a){if(void 0===e&&(e=""),void 0===n&&(n=[]),"string"!=typeof e)return!0;if(!E(e=x(e)))return!1;var t,r={url:(t=e.match(/^(?:([A-Za-z]+):)?(\/{0,3})([0-9.\-A-Za-z]+)(?::(\d+))?(?:\/([^?#]*))?(?:\?([^#]*))?(?:#(.*))?$/)||[])[0],scheme:t[1],slash:t[2],host:t[3],port:t[4],path:t[5],query:t[6],hash:t[7]},i=r.scheme,d=r.host;return a?!!a(e):!(!i||!d)&&(!f.includes(["http","https","file"],i)||("object"==typeof window&&window&&(n=o(o([],n,!0),[location.host],!1)),f.some(n,function(e){return!!(e instanceof RegExp&&e.test(d))||e===d})))}var C={a:["target","title","spellcheck","rel"],canvas:[],abbr:["title"],address:[],area:["shape","coords","alt"],article:[],aside:[],audio:["autoplay","controls","loop","preload"],b:[],bdi:["dir"],bdo:["dir"],big:[],blockquote:["cite"],br:[],caption:[],center:[],cite:[],code:[],col:["align","valign","span","width"],colgroup:["align","valign","span","width"],dd:[],del:["datetime"],details:["open"],div:["dir"],dl:[],dt:[],em:[],font:["color","size","face"],footer:[],h1:[],h2:[],h3:[],h4:[],h5:[],h6:[],header:[],hr:[],i:[],img:["alt","title","width","height","decoding"],ins:["datetime"],li:[],mark:[],nav:[],ol:["start"],p:[],pre:[],s:[],section:[],small:[],span:[],sub:[],sup:[],delete:[],form:[],strong:[],mask:["maskunits","x","y","width","height","fill"],table:["width","border","align","valign"],tbody:["align","valign"],td:["width","rowspan","colspan","align","valign"],tfoot:["align","valign"],th:["width","rowspan","colspan","align","valign"],thead:["align","valign"],tr:["rowspan","align","valign"],tt:[],u:[],ul:[],wbr:[],video:["autoplay","controls","loop","preload","height","width"],svg:["viewBox","version","xmlns","fill","width","height","stroke","stroke-width","style"],path:["d","fill","opacity","stroke","p-id","fill-rule","clip-rule","stroke-width","stroke-linecap","stroke-linejoin","fill-opacity","mask"],rect:["x","y","width","height","fill","stroke","rx"],g:[]},V={collect:null,initCollect:function(){this.collect={whiteList:{},filterProtocol:[]}},removeCollect:function(){var e=G(this.collect),n=e.count,o=e.ret;return this.collect=null,{collectKey:0===n?null:JSON.stringify(o),collectMode:"white"}},onIgnoreTagAttr:function(e,n,a){return e&&f.indexOf(["href","src"],n)>-1?V.domainWhiteList&&Array.isArray(V.domainWhiteList)&&V.domainWhiteList.length>0&&!w(a,o([],V.domainWhiteList,!0))?"":"".concat(n,'="').concat(F(a,function(e){var n;null===(n=V.collect)||void 0===n||n.filterProtocol.push(e)}),'"'):e&&(f.indexOf(["style","class","id"],n)>-1||n.indexOf("data-")>-1)?"".concat(n,'="').concat(a,'"'):(V.collect.whiteList[e]=V.collect.whiteList[e]||[],void V.collect.whiteList[e].push(n))},onIgnoreTag:function(e,n){if("style"===e)return n;m(n,function(e,n,o,a){X(A(a).html.replace("/",""),function(e){V.collect.whiteList[o]=V.collect.whiteList[o]||[],V.collect.whiteList[o].push(e)})},p)},whiteList:C,mergeWhiteList:function(e){for(var n,o={},a=0,t=f.keys(C);a<t.length;a++)o[n=t[a]]=f.from(C[n]);for(var r=0,i=f.keys(e);r<i.length;r++)o[n=i[r]]=n in C?C[n].concat(e[n]):f.from(e[n]);return o},setWhiteList:function(e){for(var n=0,o=f.keys(e);n<o.length;n++){var a=o[n];this.whiteList[a]=a in C?C[a].concat(e[a]):f.from(e[a])}}};try{var L={},_="merge";f.includes(_,"override")&&(V.whiteList=L.whiteList),f.includes(_,"merge")&&V.setWhiteList(L.whiteList)}catch(e){}var O=function(e,n){for(var o={},a=0,t=f.keys(e);a<t.length;a++){var r=t[a];Array.isArray(e[r])?o[r]=f.from(e[r]):o[r]=O({},e[r])}for(var i=0,d=f.keys(n);i<d.length;i++)(r=d[i])in e?Array.isArray(e[r])?o[r]=e[r].concat(n[r]):o[r]=O(e[r],n[r]):Array.isArray(n[r])?o[r]=f.from(n[r]):o[r]=O({},n[r]);return o},k={blackList:{a:["folder"],meta:["content"],iframe:["srcdoc"],input:["pattern"],vmlframe:["xmlns"]},blackTags:["script","xml","embed","isindex","object","base","set","handler","animate","payload","import"],blackAttrs:["charset","ns","namespace","formaction","xlink:href","xmlns:xlink","handler","repeat","repeat-start","repeat-end"],blackAttrRegExps:[/^on/],filterList:{param:["value"],video:["poster"],form:["action"]},filterAttrs:["href","src","background","style","dynsrc","lowsrc","content"]};try{var I={};I.blackAttrRegExps&&(I.blackAttrRegExps=I.blackAttrRegExps.map(function(e){return new RegExp(e.toString().slice(1,e.toString().length-1))}));var W="merge";f.includes(W,"override")&&(k=I),f.includes(W,"merge")&&(k=O(k,I))}catch(e){}var N={mode:"black",whiteList:{},blackConfig:k,collect:null,initCollect:function(){N.collect={blackList:{},blackTags:[],blackAttrs:[],blackAttrRegExps:[],filterAttrs:[],filterList:{},filterProtocol:[]}},removeCollect:function(){var e=G(N.collect),n=e.count,o=e.ret;return N.collect=null,{collectKey:0===n?null:JSON.stringify(o),collectMode:"black"}},onIgnoreTag:function(e,n){var o;if(!f.includes(k.blackTags,e))return m(n,function(e,n,o,a,t){if(-1!==o.indexOf("/"))return p(a);if(t)return"</".concat(o,">");var r=A(a),i=X(r.html,function(e,n){var a,t=0;if(k.blackList[o]&&f.includes(k.blackList[o],e)&&(N.collect.blackList[o]=N.collect.blackList[o]||[],N.collect.blackList[o].push(e),t++),k.blackAttrRegExps.length&&k.blackAttrRegExps.some(function(n){return n.test(e)})&&f.forEach(k.blackAttrRegExps,function(n){n.test(e)&&(N.collect.blackAttrRegExps.push("".concat(n.toString(),"->").concat(e)),t++)}),k.blackAttrs.length&&f.includes(k.blackAttrs,e)&&(k.blackAttrs.push(e),t++),!t){if(k.filterList&&k.filterList[o]&&f.includes(k.filterList[o],e)){var r=F(n,function(e){var n;null===(n=N.collect)||void 0===n||n.filterProtocol.push(e)});return r!==n&&(N.collect.filterList[o]=N.collect.filterList[o]||[],N.collect.filterList[o].push(e)),n?"".concat(e,"='").concat(r,"'"):e}return k.filterAttrs&&f.includes(k.filterAttrs,e)?((r=F(n,function(e){var n;null===(n=N.collect)||void 0===n||n.filterProtocol.push(e)}))!==n&&(null===(a=N.collect)||void 0===a||a.filterAttrs.push(e)),n?"".concat(e,"='").concat(r,"'"):e):n?"".concat(e,"='").concat(n,"'"):e}});return a="<".concat(o),i&&(a+=" ".concat(i)),r.closing&&(a+=" /"),a+=">"},p);null===(o=N.collect)||void 0===o||o.blackTags.push(e)}},j=function(e){var n=e.reportOnly,o=void 0===n||n,a=e.block;return o&&"all"===o?"report":("string"==typeof o&&("true"===o&&(o=!0),"false"===o&&(o=!1)),a?"enforce":o?"report":"enforce")},U=function(e){return function(o,a,t){if(!o||"string"!=typeof o)return o;var r=a;e===P&&(r=V).initCollect();var i=e(o,r);if(T(i)===T(o))return o;if(!t)return i;var d=t.logType,s=j(t),R=r.removeCollect();return y.report(n(n({type:d,disposition:s},R),{sourceText:g(o),filterText:g(i)})),"enforce"===s?i:o}},Z=U(function(e,n){return void 0===n&&(n={}),n&&n.whiteList||(n.whiteList={a:["target","href","title"],abbr:["title"],address:[],area:["shape","coords","href","alt"],article:[],aside:[],audio:["autoplay","controls","crossorigin","loop","muted","preload","src"],b:[],bdi:["dir"],bdo:["dir"],big:[],blockquote:["cite"],br:[],caption:[],center:[],cite:[],code:[],col:["align","valign","span","width"],colgroup:["align","valign","span","width"],dd:[],del:["datetime"],details:["open"],div:[],dl:[],dt:[],em:[],figcaption:[],figure:[],font:["color","size","face"],footer:[],h1:[],h2:[],h3:[],h4:[],h5:[],h6:[],header:[],hr:[],i:[],img:["src","alt","title","width","height"],ins:["datetime"],li:[],mark:[],nav:[],ol:[],p:[],pre:[],s:[],section:[],small:[],span:[],sub:[],summary:[],sup:[],strong:[],strike:[],table:["width","border","align","valign"],tbody:["align","valign"],td:["width","rowspan","colspan","align","valign"],tfoot:["align","valign"],th:["width","rowspan","colspan","align","valign"],thead:["align","valign"],tr:["rowspan","align","valign"],tt:[],u:[],ul:[],video:["autoplay","controls","crossorigin","loop","muted","playsinline","poster","preload","src","height","width"]}),new S(n).process(e)}),B=U(P),Y=function(e,n,o){var a=[],t=F(e,function(e){a.push(e)});if(t===e)return e;a=f.from(f.uniq(a));var r=n||o||{};if(!r)return t;var i=r.logType,d=j(o);return y.report({type:i,disposition:d,collectKey:a.join("___"),collectData:JSON.stringify(a),collectMode:"black",sourceText:g(e),filterText:g(t)}),"enforce"===d?t:e},$=b._xssProject||{},z=b.xssNamespace||{},J="3.0.26",q={FilterXSS:S,version:J,webpackPluginVersion:"<%= webpackPluginVersion =>",reportOnly:"<%= reportOnly =>",filterXSS:Z,_filterXSS:B,filterUrl:Y,Config:V,BlackConfig:N,project:$,setProjectName:function(e){$[e]=this,b._xssProjectName=e}};z.douyin_web=q,b.xssNamespace=z,b.Math&&!b.Math.xssNamespace&&(b.Math.xssNamespace=z),$[J]=q,b.globalThis=b,b.getFilterXss=function(){return void 0!==this._xssProjectName?this._xssProject[this._xssProjectName]:q},b.xss=q,b.isSafeUrl=w,b.isSafeDomain=w,b.isSafeProtocol=E,b._xssProject=$,b._xssProjectName&&($[b._xssProjectName]=q);var K=q.setProjectName.bind(q);e.BlackConfig=N,e.Config=V,e.FilterXSS=S,e._filterXSS=B,e.filterUrl=Y,e.filterXSS=Z,e.isSafeDomain=w,e.isSafeProtocol=E,e.isSafeUrl=w,e.project=$,e.setProjectName=K,e.setXssNamespace=function(e){var n=e.appId,o=e.bid,a=e.region;z[n]=q;V.bid=o,V.region=a,V.enabled=!0},e.xssNamespace=z,Object.defineProperty(e,"__esModule",{value:!0})}),(self.webpackChunkdouyin_web=self.webpackChunkdouyin_web||[]).push([["12870"],{718821:function(e,n,o){"use strict";var a=o(703196),t=o(545727);let r=(0,t.A)(function(e){return a.createElement("svg",Object.assign({viewBox:"0 0 24 24",fill:"none",xmlns:"http://www.w3.org/2000/svg",width:"1em",height:"1em",focusable:!1,"aria-hidden":!0},e),a.createElement("path",{fillRule:"evenodd",clipRule:"evenodd",d:"M7.44 19.8a1.5 1.5 0 0 1 0-2.13l5.66-5.65-5.66-5.66a1.5 1.5 0 1 1 2.12-2.12l6.72 6.72a1.5 1.5 0 0 1 0 2.12L9.56 19.8a1.5 1.5 0 0 1-2.12 0Z",fill:"currentColor"}))},"chevron_right");n.Z=r},788711:function(e,n,o){"use strict";var a=o(703196),t=o(545727);let r=(0,t.A)(function(e){return a.createElement("svg",Object.assign({viewBox:"0 0 24 24",fill:"none",xmlns:"http://www.w3.org/2000/svg",width:"1em",height:"1em",focusable:!1,"aria-hidden":!0},e),a.createElement("path",{fillRule:"evenodd",clipRule:"evenodd",d:"M11.43 2.1A1 1 0 0 1 12 3v18a1 1 0 0 1-1.62.78L4.65 17H2a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h2.65l5.73-4.78a1 1 0 0 1 1.05-.12Zm2.52 6.33a1.5 1.5 0 0 1 2.12.02 4.99 4.99 0 0 1 0 7 1.5 1.5 0 1 1-2.14-2.1 1.99 1.99 0 0 0 0-2.8 1.5 1.5 0 0 1 .02-2.12Zm4.9-4.28a1.5 1.5 0 0 0-1.7 2.47 6.5 6.5 0 0 1 0 10.76 1.5 1.5 0 0 0 1.7 2.47 9.5 9.5 0 0 0 0-15.7Z",fill:"currentColor"}))},"volume_2");n.Z=r},583646:function(e,n,o){"use strict";function a(e){if(!Uint32Array.from){for(var n=new Uint32Array(e.length),o=0;o<e.length;)n[o]=e[o],o+=1;return n}return Uint32Array.from(e)}o.d(n,{r:function(){return a}})},575756:function(e,n,o){"use strict";o.d(n,{Z:function(){return t}});let a=`
Radeon RX 7900 XT|2202
Radeon RX 7900 XT|1968
RX 6800 XT|1957
Radeon RX 6900 XT (XTXH)|1930
Radeon RX 6900XT|1925
Radeon PRO W6900X|1889
RX 6900 XT|1852
Radeon RX 6900|1814
Radeon RX 7900 XTX|1773
RX6800|1695
FreddyVGA|1603
Radeon PRO W6800|1564
Radeon RX 7900 XTX|1437
Radeon RX 6950 XT|1376
Radeon RX 6800 XT|1358
Radeon RX 6750 XT|1310
Radeon(TM) RX 6850M XT|1294
Radeon RX 6700|1285
Radeon RX 6900 XT|1269
Sapphire Nitro+ RX 6800|1262
Radeon PRO W6800X|1255
Radeon PRO W6800X Duo|1218
Radeon RX 6700|1214
Radeon RX 6800 XT|1183
Sapphire Nitro Radeon RX6650XT|1180
Radeon(TM) RX 6750 XT|1166
Radeon RX 6800|1163
Radeon RX 6900 XT|1162
ASRock RX 6650 XT Phantom Gaming|1161
Radeon Navi23|1139
Radeon RX 6650 XT|1132
Radeon RX 6950 XT|1130
Radeon 6800|1121
Radeon RX 6700 XT|1110
Radeon Pro W6600X|1101
Radeon RX 6700M|1081
Radeon RX 6800M|1078
Radeon RX 5700 XT PJM|1060
Radeon RX 6800|1054
Radeon RX 6600 XT|1037
Radeon RX 6600 XT|1031
ASUS RX 6600XT macOS Edition|1021
Radeon RX 6800M|1016
Radeon Pro Vega II Duo|1015
Radeon RX 5700 Series|961
Radeon RX 6800/6800 XT / 6900 XT|961
Radeon RX 6600 XT|958
Radeon Pro Vega II|956
Radeon RX 6650 XT|951
Navi 10 5700 XT|947
Radeon Pro Vega II|947
Radeon RX 5700 Series|946
Radeon Pro W5700X|934
Radeon RX 6600|929
ASUS Radeon RX 5700 XT|926
Radeon Pro W5700X|917
Radeon Pro 5700 XT|917
Radeon RX 6900 XT|915
Radeon RX 5700 XT|911
Radeon Pro W5700|895
Radeon RX 6600/6600 XT/6600M|889
Radeon RX 6750 XT|883
Radeon RX 6600|874
Radeon RX 5700|855
Radeon RX 5700 XT 50th Anniversary|854
Radeon VII|851
Radeon RX 5700 XT 50th Anniversary|845
Radeon PRO W6800|837
Radeon Pro Vega 64|824
Radeon Navi10|822
Radeon RX 5600 XT|816
Radeon RX 6600M|803
Radeon RX 6800S|791
Radeon Pro 5700 XT|781
Radeon RX Vega 64 8GB|775
Radeon Pro 5700|768
Radeon Vega Frontier Edition|767
Radeon RX Vega|766
Radeon RX Vega 56/64|765
Radeon(TM) RX Vega|756
Radeon Pro Vega 64X|745
Radeon RX 5600 XT|744
Radeon PRO W6600|744
Radeon Vega 64 LC|735
Radeon RX Vega 64.1|732
Radeon RX 6600M|728
Radeon Pro 5700|714
Radeon Vega Frontier Edition|707
Radeon Vega Frontier|704
Radeon Vega FE|701
Radeon RX 5700 XT|691
Radeon Pro Vega 64|673
Radeon Vega 64|667
Radeon VII|663
Radeon Pro WX9100|656
Sapphire Radeon RX Vega 64 8GB|654
Radeon(TM) PRO W6600M|654
Radeon RX 5700 XT 50th Anniversary|652
Radeon RX 5700|640
Radeon Pro W5700|640
Radeon(TM) Pro WX 9100|635
Radeon RX Vega 56|628
Radeon RX Vega 56|623
Radeon Pro 5500 XT|622
Radeon RX 5600 OEM/5600 XT / 5700/5700 XT|621
Radeon RX 5500|618
Radeon RX 5500 XT|617
Radeon Vega Frontier Edition|617
Radeon RX 5500M Series|613
RX xxx|613
Radeon Pro Vega 64X|611
Radeon RX Vega 64|610
Radeon RX 5600 XT|610
Radeon Pro Vega 64|605
Radeon RX 6500 XT|603
Radeon Vega|602
Radeon Pro W5500|601
Radeon RX 5600M|600
Radeon Pro Vega 56|598
Radeon Pro Vega 64|594
Radeon Pro 5600M|593
Radeon Pro Vega 48|592
Radeon Pro Vega II Duo|590
Radeon RX 590 Series|589
Radeon RX Vega 56 8GB|589
Radeon Pro 5600M|589
Radeon Pro WX 9100|588
Radeon Pro 5300|584
Radeon(TM) R9 Fury Series|579
Radeon RX 6800 XT 16GB|567
Radeon Pro 5600M|567
Radeon Pro W5500X|564
Radeon(TM) RX 5500M|559
Radeon HD 7870|556
Radeon Pro W5500|554
Radeon RX 5500M|550
Radeon R9 290X Series|549
66AF:F0|548
Radeon Pro 5500 XT|547
Radeon RX 580 Series|547
Radeon RX 5500XT|547
Radeon(TM) RX 580X|546
Radeon Pro 5500 XT|545
Radeon(TM) Pro W5500M|544
Radeon Pro W5500X|544
Radeon Pro W5500|541
RadeonT RX 5300|537
Radeon(TM) RX 570 Graphics|524
Radeon Pro 5300|522
Radeon(TM) RX 6500M|521
Radeon RX Vega M GL|520
ASUS Radeon RX 570 Series|519
ASUS Radeon RX 580 Series|518
Radeon(TM) RX 580|518
Radeon(TM) Pro V7350x2|518
Radeon(TM) RX 480 Graphics|516
Radeon(TM) RX 570 Graphics|515
Radeon RX 6400|513
Radeon Pro 580X|513
Radeon(TM) R9 390 Series|503
Radeon Pro 5300|500
Radeon RX 580 2048SP|500
Radeon PRO W6400|500
Radeon RX 570 Series|499
Radeon PRO W6800X Duo|497
Radeon Pro 580|494
Radeon RX 5500 XT|493
Radeon RX 6400|487
Radeon Pro 580|485
Radeon(TM) Pro WX 7100 Graphics|485
Radeon(TM) R9 290X|478
Sapphire Radeon RX 580 Pulse|477
Radeon RX 6700/6700 XT / 6800M|476
Radeon(TM) RX 580|475
Radeon RX 6700S|475
Radeon R9 290X|470
Radeon(TM) RX 470 Graphics|469
Radeon R9 FURY / NANO Series|468
Radeon Embedded E9560|467
Kamen Rider Black RX|466
Radeon(TM) E9550|464
Radeon(TM) RX 580 Graphics|463
Radeon RX Vega 56/64|463
Radeon(TM) RX 480|462
Radeon RX 6800 XT|462
Radeon RX 470 Series|461
Radeon RX480|456
66AF:F1|455
Radeon Pro 480/575|455
Radeon Embedded E9560|450
Radeon FURY|450
Radeon RX 5600 OEM/5600 XT / 5700/5700 XT|447
Radeon RX 6600 XT|446
Radeon HD 6800 Series|445
Radeon Pro 570X|444
Radeon(TM) RX 470 Graphics|443
Radeon Pro 575X|443
Radeon RX 470/480/570/570X/580/580X/590|443
Radeon RX 6600|443
Radeon RX Vega M GH Graphics|441
RX 580|440
Radeon RX 570|440
Radeon Pro 570|440
Radeon RX 590|437
Radeon(TM) RX 470 Series|435
Radeon RX 6900 XT|435
Radeon FURY X|434
RX 590|431
Radeon Pro 5500M|430
???|430
Radeon(TM) RX 570|430
Radeon RX 580|429
Radeon HD 8xxx|426
Radeon R9 290|425
Radeon Pro 5500M|420
Radeon Pro 580X|420
Radeon RX 6700 XT|420
Radeon RX 480|419
Radeon R9 290/390|418
Radeon Pro 580X|416
Radeon(TM) Pro Duo|414
Ellesmere Radeon RX 570|411
Radeon R9-290X|411
Radeon Pro 580|411
Radeon R9 200 Series|406
Radeon RX 570|406
Radeon Pro 470/570|404
Radeon RX 6800M|404
Radeon RX 5300M|400
Radeon RX 580 Series (POLARIS10, DRM 3.40.0, 5.11.9-141-tkg-pds, LLVM 11.1.0)|399
Radeon Pro 5300M|399
Radeon R9 285|398
Radeon RX 470|393
Radeon Pro 575|392
Radeon Pro 575X|391
Radeon Pro WX 7100|387
Radeon RX 6700M|386
Radeon RX 470/480/570/570X/580/580X/590|382
Radeon PRO W6600|376
Radeon Polaris|374
Radeon RX 6500 XT|374
Radeon Pro Vega 20|371
Radeon HD 7970|370
Radeon Pro Vega 16|370
Radeon RX 6800|369
Radeon Pro Vega 64 OpenGL Engine|369
Radeon(TM) R9 380 Series|367
Radeon RX 5700XT|366
FirePro W8100|366
Radeon Pro Vega 64|365
Radeon Pro 570|365
Radeon Pro 570X|363
Radeon Pro Vega 64 OpenGL Engine|362
Radeon R9 280x|362
Radeon R9 380|362
Radeon R9 280x|361
Radeon R9 280x|360
Radeon Pro Vega 56|360
R9 280X Dual-X|359
Radeon Pro Vega 56 OpenGL Engine|356
Radeon HD 7970|355
Radeon HD 7970X/8970/R9 280X|354
Radeon R9 285|353
Radeon R9 380X|352
Radeon RX 480|352
Radeon RX 5700 XT Series|350
ASUS Radeon RX 470 Series|350
Radeon Pro Vega 64|349
Radeon R9 200 / HD 7900 Series|346
ASUS Radeon RX 470 Series|346
Radeon Vega 56|346
Radeon RX 580 Series (AMD POLARIS10 / DRM 3.15.0 / 4.12.0-1-amd64, LLVM 4.0.1)|343
Radeon Pro Vega 20|343
R9 380|341
Radeon HD 7970|338
Radeon RX 5700 XT|336
Radeon D700|336
Asus Radeon R9 280|334
Radeon R9 285|334
Radeon R9 M395X|332
Radeon RX 5600 XT|332
PowerColor Radeon R9 280|330
Radeon R9 280|329
FirePro W7100 Graphics Adapter|328
Radeon R9 M295X Mac Edition|327
ASUS Radeon RX 5700|327
Radeon R9 380|326
Radeon Pro Vega 16|325
Radeon R9 290X|325
Radeon RX5600|324
ASUS Radeon RX 5500 XT|323
Radeon R9 280|323
Radeon HD 7950/8950 / R9 280|321
Radeon R9 M395|319
Radeon RX 6800/6800 XT / 6900 XT|318
FirePro D700 (FireGL V)|318
Radeon RX 5500/5500M / Pro 5500M|318
MSI Radeon RX 6600 XT Gaming X|318
FirePro W8000|315
Radeon HD 7950|315
Radeon Pro W5700|315
FirePro W7170M|314
Radeon PRO W6800|314
Radeon RX 5500|313
Radeon RX 580 Special Edition|312
RadeonT RX 5500M|311
Radeon R9 M395 (Bootcamp XG edition by bootcampdrivers.com)|311
Radeon R9 360|309
Radeon Pro WX 7100|307
Radeon Pro WX 7100 Mobile|307
Radeon RX 5700 XT 50th Anniversary|307
R9 xxx|303
Radeon RX 5700XT|302
Radeon PRO W6400|301
Radeon(TM) R9 370 Series|301
Radeon RX 470/480/570/570X/580/580X/590|300
Radeon(TM) PRO W6600M|298
Radeon HD 8950|298
Radeon R9 M395X|297
Radeon R9 M395X|296
RX Vega 64|296
Radeon RX Vega 11 Graphics|295
Radeon Pro 270X|294
Radeon RX 580 2048SP|290
Radeon HD 7950|290
Video Controller (VGA Compatible)|290
Radeon(TM) R7 370 Series Graphics|290
Radeon HD 7950|290
Asus Radeon R9 270X|289
Radeon RX 580X Series|288
Radeon(TM) RX 5500M|285
Radeon R9 270X|285
RX xxx|285
ASUS R7 265 Series|281
Radeon(TM) R9 270|280
731F:C1|280
Radeon R9 M395X|279
Radeon(TM) R7 370 Series|279
Radeon Pro V520 MxGPU|278
Radeon R9 M395|277
FirePro D700|277
Radeon R9 270X|277
Radeon(TM) R9 200 Series|276
Radeon RX 5700|275
Radeong 0.4 on AMD POLARIS10 (DRM 3.8.0 / 4.9.11-1-ARCH, LLVM 3.9.1)|274
Radeon HD 7870 XT|274
Radeon R9 390X|272
Radeon(TM) RX 570 Graphics|272
Radeon HD 7870 GHz Edition|271
Radeon R9 390|270
FirePro D700|269
Radeon R9 M395|268
Radeon R9 270|268
Radeon RX 5700 / 5700 XT|267
ASUS R7 370 Series|267
FirePro W7000|266
Radeon(TM) Pro V7350x2|266
Radeon(TM) RX 470 Series|266
Radeon RX Vega 64 OpenGL Engine|266
Radeon RX 5500M|265
Radeon HD 7950/8950 OEM / R9 280|265
Radeon Vega Frontier Edition OpenGL Engine|265
Radeon 7950 x2|263
Radeon R9 270|263
Radeon VII|263
Radeon HD 7xxx|262
Video Controller (VGA Compatible)|262
Radeon(TM) RX 570|261
Radeon RX 5500 XT|261
Radeon R9 M295X|261
FirePro W7000 (FireGL V) Graphics Adapter|260
Radeon R9 M390|260
Radeon HD 7870 GHz Edition|260
Radeon R9 M390 (Bootcamp edition by bootcampdrivers.com)|260
Radeon R9 370|259
Metal|259
Radeon HD 7870|259
Radeon RX 470/570|258
Radeon(TM) R9 370|257
Radeon(TM) RX 460|257
Radeon RX 560 Series|256
Radeon R9 290|255
Radeon(TM) RX 560 Series|255
Radeon RX 5300M|254
FirePro W7000|254
Radeon R9 290X|253
67EF:E7|253
Radeon HD 7850|253
Radeon(TM) RX 460 Graphics|253
MSI Radeon RX 580|251
Radeon R9 290/390|250
FirePro W8100 (FireGL V)|249
Radeon Pro WX 9100 OpenGL Engine|248
Radeon(TM) RX 560|247
Radeon(TM) RX 560 Series|247
Radeon Pro Vega II Duo|247
Radeon HD 7970M|246
Radeon R9 290|245
Radeon RX 5600M|245
FirePro D300|245
Radeon(TM) RX 5600M Series|244
Radeon RX 590 Series|244
Radeon R7 370 Series|244
Radeon(TM) RX 560|243
FirePro D300|243
Radeon R9 390|243
Radeon RX 470/480/570/570X/580/580X|243
FirePro D300|243
Radeon(TM) R7 370 Series|242
Radeon R9 M390|241
Radeon RX 560X Series|241
FirePro D300|241
Radeon RX 560|240
Radeon R9 M290X|240
Gigabyte Vega 64 macOS Edition|239
Radeon Pro 580|238
Radeon Pro WX 4100|236
Radeon Pro WX 7100 OpenGL Engine|236
Radeon HD - FirePro D300|235
FirePro D500|234
Radeon Pro 580 OpenGL Engine|234
Radeon(TM) E9260|234
Radeon Pro WX 2100|233
FirePro D500|232
FirePro D500|232
Radeon(TM) RX 6500 XT|232
Radeon Pro 580X|231
Radeon HD 7850|231
Radeon Pro 575|231
Radeon Pro Vega 64X|231
ASUS R9 270 Series|230
Radeon Pro 450|230
Radeon(TM) RX 560 Graphics|230
Radeon R9 M290|229
Radeon Pro 560X|228
Radeon Pro 480/575|228
Pitcairn PRO Radeon HD 7850|228
ASUS Radeon RX 5700 XT|227
Radeon HD 7870|227
Radeon(TM) Pro WX 5100 Graphics|226
Radeon R9 370X|225
Radeon(TM) RX 480|224
Radeon HD7970M|224
FirePro S9000 (FireGL V)|223
Radeon RX 550 640SP / RX 560/560X|222
MSI / AMD RX 560 4G|222
Radeon RX 570 OpenGL Engine|222
MSI RX650|222
RX 480|221
MSI / AMD RX 560|221
Baffin AMD Radeon RX 560|221
MSI Baffin RX650|220
Radeon Pro 5700 XT|220
Radeon Pro 570|220
Radeon Pro 575 OpenGL Engine|219
Asus Radeon R9 270X|219
Radeon RX RX 560|218
Radeon RX 560 [Baffin]|218
RX 460|218
Radeon R9 370X|218
Radeon(TM) Pro WX 4100|217
ASUS R9 390 Series|217
Radeon Pro 5600M|217
R9 xxx|217
Radeon HD 7870 Series|217
Radeon Pro RX 560|216
R9 280X Dual-X|215
Radeon Pro 570 OpenGL Engine|214
RX 560|213
Radeon Pro WX 5100|213
FirePro D700|213
Radeon(TM) R9 390 Series|213
Radeon RX 480|212
Radeon RX 560|212
Radeon RX 5500/5500M / Pro 5500M|212
Radeon RX 550 640SP / RX 560/560X|211
Radeon R9 FURY / NANO Series|211
Sapphire Radeon RX 560|211
Radeon RX 460|210
Radeon RX550/550 Series|210
inc. Radeon RX 480|209
Radeon(TM) RX 550|208
Radeon R9 M290X|206
Radeon Pro 560 (Bootcamp XG edition by bootcampdrivers.com)|206
Radeon RX460|206
Radeon RX 550 Series|205
Custom GPU 0405|204
Radeon(TM) RX 460|204
ASUS AMD Radeon R9-990X|204
Radeon Pro 555X|203
Radeon RX 460/560|203
Radeon HD 7970X/8970/R9 280X|202
ASUS Radeon RX 550 Series|201
Radeon HD 8950|201
FirePro D500 (FireGL V)|201
RX 5700XT|200
Radeon 550 Series|200
Radeon HD 8470 + 7660D Dual Graphics|200
Radeon HD 7990|200
Radeon RX 560X|199
Radeon RX Vega|199
Radeon HD 7950 Series|198
Radeon(TM) RX 540|197
Radeon HD 6970|197
Radeon HD 7970/8970 / R9 280X|197
Radeon Navi14|197
Radeon Pro 560|197
Radeon RX 550|197
Radeon R9 285|196
Radeon Pro W5500|195
Radeon Pro Vega 56|195
Radeon Pro 460|195
Radeon RX 470/480|194
Radeon PRO Graphics|194
Radeon(TM) RX550|194
Radeon Pro 560X|193
Radeon Pro 570X|192
66AF:F1|192
Radeon RX Vega M GH|190
Radeon R9 M280X|190
Radeon RX 460/560D / Pro 450/455/460/555/555X/560/560X|189
Radeon R9 280,|188
Custom GPU 0405|188
Radeon HD 7790|187
Radeon(TM) RX 480 Graphics|187
Radeon Pro 455|186
Radeon R9 260|186
Radeon RX 580 Series|186
Radeon HD 7950/8950 OEM / R9 280|186
Radeon R9 290X|185
Radeon R9 M290X|184
Radeon(TM) R9 370 Series|184
Radeon Pro 555|184
Radeon R7 260X|184
Radeon HD 6950|183
FirePro W5000|183
Radeon(TM) R9 390X|182
R9 270X Devil|182
Radeon(TM) RX 470 Graphics (AMD POLARIS10 / DRM 3.23.0 / 4.15.0-1-MANJARO, LLVM 5.0.0)|182
Radeon R9 380|182
Radeon(TM) Pro WX 9100|182
Radeon(TM) R7 360 Series|181
Radeon RX 570 Series|181
Radeon(TM) R9 M470X|181
Radeon(TM) R7 360 Series|181
Radeon RX480|180
Radeon R7 200 Series|180
Radeon Pro WX 4150|180
Radeon Pro WX 4100|179
Radeon HD 8xxx|179
ASUS R9 295X2 Series|179
Radeon R9 390X|178
Radeon HD 5870|176
Radeon Pro 560|176
Radeon RX 580 OpenGL Engine|175
Radeon HD 8950|175
FirePro V(FireGL V) Graphics Adapter|175
ASUS Radeon RX 580 Series|174
Radeon Pro WX 4100|174
Radeon Pro 460|173
Radeon HD 2600 XT|173
Radeon Pro WX 4100|172
Radeon HD 8280|172
Radeon Pro 575|171
Radeon Pro 555X|171
Radeon Pro WX 4130/4150|170
Radeon RX Vega M GH Graphics|170
FirePro W5100|170
Radeon(TM) PRO WX 8200|169
Radeon Vega Frontier Edition|169
Radeon Pro 555X|168
FirePro D700|168
Radeon HD 6990|167
Radeon RX 470 OpenGL Engine|167
Radeon HD 7870 XT|167
Radeon RX 580|167
Radeon Polaris|167
FirePro V8800 (FireGL V)|166
Radeon RX 550|165
Radeon HD 6900 Series|165
FirePro W9100 (FireGL V)|164
RX 580|163
Radeon(TM) RX 580X|163
Radeon RX 550|163
Radeon HD 6870|163
Radeon R9 M395X OpenGL Engine|163
Radeon(TM) R9 360|163
Radeon(TM) HD 8490|162
Radeon R9 M295X|162
Radeon HD 7970M|162
Radeon R9 M380|161
FirePro W5100 (FireGL V) Graphics Adapter|161
ASUS HD7850 Series|161
FirePro M6100 FireGL V|161
Radeon Pro 455|160
Radeon RX 460/560D / Pro 450/455/460/555/555X/560/560X|160
Radeon R9 M395X|159
Radeon RX 560X|159
Radeon Pro 555|158
RadeonT RX 560X|158
Radeon Pro Vega 48|158
ASUS Radeon RX Vega|158
Radeon Pro WX 9100|158
Radeon Pro Vega 64|157
Powered By QiongB A9999999999|157
Radeon(TM) Pro Duo|157
FirePro D700|157
Radeon Pro WX 7100|156
Radeon RX 460|156
Radeon HD - FirePro D700 OpenGL Engine|156
Radeon R9 M290X|156
Radeon R9 M395 OpenGL Engine|155
Radeon Pro SSG|155
FirePro D300|155
ASUS R9 380 Series|155
Radeon(TM) R9 Series|153
Radeon RX 470/480/570/580|153
FirePro W8000|153
Cezanne|153
Radeon(TM) Graphics|153
FirePro D300|153
Radeon(TM) R9 Fury Series|153
Radeon R9 M395|152
Radeon RX 570|152
Radeon R9 270X Series|152
Radeon Pro 5300M|152
R9 xxx|152
Radeon Pro 555|152
FirePro D500|151
Radeon HD 5850|151
FirePro D300|150
Radeon(TM) R9 290X|150
66AF:F0|149
Radeon(TM) RX 560|149
Radeon R9 M290|148
Radeon Instinct MI25 MxGPU|148
FirePro V7800 (FireGL) Graphics Adapter|148
Radeon(TM) R9 M470|147
Advanced Micro Devices, Inc. [AMD/ATI] Fiji [Radeon R9 FURY / NANO Series]|147
Radeon HD 5870 Series|147
Radeon(TM) E9550|147
Radeon HD 7850|147
Radeon HD 7770|147
Radeon Pro Vega 20|146
Radeon R9 290/390|146
Radeon Pro 450|146
Radeon RX 560X Series|146
Radeon HD 6850|146
Radeon R9 270 1024SP|145
ASUS R9 280X Series|145
Radeon Pro 450|145
Radeon(TM) R9 390 Series|145
FirePro V7900 (FireGL V)|145
Radeon R9 370X|145
Radeon(TM) RX 560 Series|144
ASUS R7 250X|144
Radeon RX 480 OpenGL Engine|144
Radeon R9 290X|144
Radeon RX 550X|144
Radeon(TM) RX 580|144
ASUS Radeon(TM) RX 470 Series|143
Baffin Radeon RX 560|143
Radeon R9 M295X (Bootcamp edition by bootcampdrivers.com)|143
Radeon R9 M295X Mac Edition|143
Radeon R7 Series / HD 9000 Series|142
Advanced Micro Devices [AMD] nee ATI Device|142
Radeon(TM) Pro WX 7100 Graphics|142
Radeon RX 640|142
FirePro D500|141
Radeon HD 7900 Series|141
Radeon R9 290|141
Radeon R7 250X|141
Radeon(TM) RX Vega|140
Radeon 630 Series|140
FirePro W8100 Graphic Adapter|140
Radeon R9 FURY / NANO Series|140
Radeon R9 M390|140
Radeon Pro WX 3100|140
Radeon R9 290|140
Radeon(TM) R9 370|140
FirePro V7900|139
Radeon HD 7970|139
Radeon HD - FirePro D500 OpenGL Engine|139
Radeon HD - FirePro D300 OpenGL Engine|139
Radeon Pro 580|139
Radeon HD 7770|139
Radeon HD - FirePro D500 OpenGL Engine|139
Radeon 540/540X/550/550X / RX 540X/550/550X|138
FirePro S9050|138
Radeon(TM) RX 480 Graphics|138
Radeon(TM) R9 M390X|137
Radeon Vega 64|137
Radeon(TM) Graphics|137
Tonga PRO GL [FirePro W7100]|136
HD7950 Martin Ver.|136
Radeon HD 7990|135
Radeon R9 280x|135
Radeon RX550/550 Series|135
HD7950 MARTIN REV.|134
Radeon RX560|134
Radeon R7 250X Series|134
Radeon R9 M390 OpenGL Engine|134
ASUS R7 250X|134
Radeon HD6870|134
Radeon R9 270X|134
Radeon Pro 5500 XT|134
Radeon(TM) RX 480|133
Radeon R9 270|133
ASUS HD7970 Series|133
Radeon RX 540|133
Radeon 500 Series|132
Radeon HD 5970|132
Radeon HD 7770 GHz Edition|132
Radeon HD 5870|132
Radeon 540X Series|132
Radeon HD 6870 Series|132
Radeon(TM) RX 470 Graphics|132
Radeon HD - FirePro D300 OpenGL Engine|132
Radeon HD 7xxx|131
Radeon HD 5970|131
RadeonT 540X|131
Radeon R7 Graphics + R7 350 Dual Graphics|131
Radeon R9 M295X Mac Edition / R9 380X|131
Firepro M5100|131
Radeon(TM) R9 M375X|131
Radeon R9 280x|130
Radeon(TM) RX 560X|130
Radeon HD 6990|130
Radeon Pro 5500M|130
Radeon Pro WX 5100 OpenGL Engine|129
Radeon R9 M395X (Bootcamp edition by bootcampdrivers.com)|129
Radeon R9 M380|128
FirePro W5170M|128
Radeon R9 280|128
FirePro W5000 (FireGL V)|128
Radeon(TM) RX 5600M Series|128
Radeon RX 560D|128
FirePro D500 (FireGL V)|128
Radeon(TM) Pro WX 5100 Graphics|128
Radeon(TM) RX Vega 11 Graphics|128
Radeon HD 7970|127
Radeon R9 370|127
Radeon HD 7770|127
Radeon R9 M395X|126
Radeon HD 7660D|126
Radeon HD 8970|126
Radeon R9 200 Series|126
Radeon Pro WX 3200 Series|126
Radeon HD 7800 Series|125
Radeon R9 285/380|125
Radeon R9 270X|124
FirePro W2100|124
FirePro W7170M|124
Radeon HD 7870 GHz Edition|123
Radeong 0.4 on AMD TONGA (DRM 3.1.0, LLVM 3.9.0)|123
Radeon RX 460|123
Radeon HD 5970 Series|123
Radeon R9 M380|122
Radeon R9 M395|122
Asus Radeon R9 280|122
Radeon HD 6850 Series|122
Radeon(TM) RX 540|122
Radeon HD 6900 Series|122
Device|122
67DF:C4|121
Radeon HD 6950|121
FirePro D300 (FireGL V)|121
Radeon RX 570|121
Radeon HD 5850 Series|121
Radeon HD 7870 XT|121
Radeon HD 7950|121
FirePro V7800 (FireGL) Graphics Adapter|121
Radeon HD 6850|121
Radeon HD 7950|120
Radeon HD 7870 GHz Edition|120
Radeon R7 370 / R9 270X/370X|120
Radeon HD 6870|120
Radeon Pro V340|120
ASUS Radeon RX 570 Series|119
Radeon(TM) R7 370 Series Graphics|119
Radeon(TM) RX 580 Graphics|119
Radeon(TM) RX 470 Graphics|119
Radeon HD 5870|119
Radeon HD 7950/8950 / R9 280|119
Radeon HD 6790|119
Radeon(TM) RX580|119
ASUS ARES2|119
Radeon(TM) R9 380 Series|118
Radeon HD 7750|118
Radeon Pro 560X|118
Radeon R7 250E|118
Radeon 550 Series|118
Radeon RX 560|118
Radeon Pro WX 5100|117
Radeon R7 370 / R9 270X/370|117
Radeon HD 7800 Series|117
FirePro W5000 (FireGL V) Graphics Adapter|117
Radeon HD 7750 Series|116
Radeon HD 5870|116
Radeon R7 450|115
FirePro R5000|115
Radeon R7 370 Series|115
FirePro W9100|114
Radeon R7 370 / R9 270/370|114
Radeon(TM) 540 Graphics|114
Radeon HD 6510 Series|114
Radeon(TM) R7 370 Series|113
Sapphire Radeon HD6870|113
Firepro M5100|113
Radeon(TM) RX 550|113
Radeon(TM) Pro Duo|113
Radeon 540/540X/550/550X / RX 540X/550/550X|113
Radeon Pro 570|112
Radeon R9 280|112
FirePro D700 (FireGL V)|112
(ATI) FirePro M6000 (FireGL V) Mobility Pro Graphics|112
Renoir|112
Radeon 540X Series (POLARIS12, DRM 3.40.0, 5.10.56-1-MANJARO, LLVM 12.0.1)|112
Radeon HD 6970|112
Radeon HD 8770|112
Radeon Pro WX3200 Graphics|112
Radeon(TM) R9 270|111
Radeon R9 270X|111
Radeon R9 285|111
Radeon HD 7800M Series|111
Radeon(TM) R7 370 Series|111
Radeon HD 7870M Series|111
Radeon Pro 450/550|110
Radeon HD 7000 series|110
Radeon HD 7870|110
Radeon Pro 555X|110
Radeon RX590 GME|109
FirePro S10000|109
Radeon HD 7870M|109
Radeon HD 5800 Series|109
Radeon HD 6970M|108
ASUS HD7770 Series|108
Radeon(TM) R9 M360|108
Radeon(TM) RX 550X|107
Radeon R9 285|107
Radeon HD 6900M Series|107
Radeon HD 7870 GHz Edition|107
FirePro S7000|107
Radeon R9 M370X|106
Radeon Pro WX 4100|106
Radeon HD 6800 Series|106
Radeon HD 7750|106
Radeon Pro 455 OpenGL Engine|106
ASUS R7 370 Series|106
Radeon Pro 560|105
Radeon HD 6870|105
FirePro D300 (FireGL V)|105
Radeon HD 6970M|105
Radeon HD 7850|105
Radeon(TM) R9 200 Series|104
ASUS HD7750 Series|104
Radeon HD 6970M OpenGL Engine|104
Asus Radeon R7 250|104
Radeon R7 370 / R9 270X/370|104
Radeon R9 M395X (Bootcamp XG edition by bootcampdrivers.com)|103
Radeon(TM) RX 560|103
Radeon RX Vega|103
Radeon(TM) Pro W5500M|103
Radeon R9 270|103
Radeon Pro 560X|103
Radeon HD 5850|103
FirePro S7150|103
Radeon(TM) RX 580|103
Radeon(TM) R9 370 Series|103
ASUS Radeon(TM) RX 480 Series|102
Radeon Graphics Processor|102
Radeon R9 M370X|102
FirePro W7100|102
Radeon R9 M370X|101
Radeon Pro 460 OpenGL Engine|101
Radeon RX 580 Series|101
Radeon 500 Series|100
Radeon Pro 555|100
Radeon(TM) Pro WX 4100|100
Asus Radeon R7 260X|100
Radeon(TM) RX Vega 10 Graphics|100
Radeon HD 7790|99
Radeon Pro 450 OpenGL Engine|99
Radeon HD 7790/8770 / R7 360 / R9 260/360|99
FirePro M4000 Mobility Pro Graphics|99
Radeon HD 7970M|99
Radeon R9 M270X|99
Radeon RX 550|98
Radeon HD 6850|98
Radeon(TM) RX 460|98
Radeon(TM) RX Vega11 Graphics|98
Radeon(TM) RX 460 Graphics|98
Radeon Pro 460|97
Radeon HD 7800 Series|97
Matrox C680 PCIe x16|97
Radeon(TM) RX 550|97
Radeon HD 5770|96
Radeon HD 8670D + 7700 Dual Graphics|96
Radeon HD 7790|96
Radeon 630 Series|96
Radeon RX 560 Series|96
Firepro M6100|95
Radeon HD 6700 Series|95
67EF:E7|95
Radeon(TM) Vega 10 Graphics|95
Radeon HD 6900M Series|94
Radeon Pro 455|94
FirePro M4000|94
Radeon R9 260|94
FirePro W7000|94
Radeon Instinct MI25|93
Radeon HD 8870M|93
Radeon(TM) Vega 11 Graphics|93
Radeon Pro 450|93
FirePro W5000|92
Radeon HD 6770|92
Radeon(TM) RX560|92
Radeon(TM) Graphics|91
ASUS Radeon(TM) RX 460 Series|91
Radeon(TM) Vega 8 Graphics|91
Radeon(TM) Graphics|91
FirePro W5100 Graphics Adapter|90
Radeon(TM) Pro WX Series|90
Renoir|90
STRATO XT (6646)|89
Radeon(TM) Pro WX 4150 Graphics|89
Radeon E8870MXM|89
Radeon HD 8970M|89
FirePro M6100 FireGL V|89
Radeon HD 7770|89
FirePro W5100 (FireGL V) Graphics Adapter|89
Radeon HD 6970M|89
Radeon Pro 460|88
Radeon RX Vega 8 Graphics|88
Radeon HD 7700 Series|88
Radeon(TM) R9 M360|88
ASUS R7 265 Series|88
Radeon RX Vega M GL Graphics|88
ASUS Radeon RX 550 Series|88
Radeon R7 360 / R9 360|88
Radeon HD 6950|86
Radeon HD 6790|86
Radeon Pro WX 2100|86
ASUS Radeon RX 560 Series|86
Radeon HD 5750|86
Radeon(TM) RX 640|86
Radeon HD 8870M|85
Radeon R7 260X|85
Radeon Pro WX 7100|85
Radeon(TM) R7 360 Series|85
Radeon Infoshock\u2122 RX 460 Graphics|85
FirePro W5170M|85
Radeon R9 M295X|85
FirePro W8100|85
Radeon HD 6750|85
FirePro W5170M|85
FirePro V5800 (FireGL) Graphics Adapter|84
ASUS R7 250X|84
67E8:00|84
Radeon(TM) RX 550X|84
Radeon(TM) R7 350|84
Radeon(TM) E9260|84
Radeon Sky 500|84
Radeon R9 M270X|83
Radeon(TM) R9 350|83
Radeon(TM) RX Vega 11 Graphics|83
Firepro M6100|83
Radeon R9 360|82
FirePro V7900|82
FirePro V5800 (FireGL V)|82
Radeon HD 8830M|82
Radeon Pro 450|82
Radeon HD 8950|82
6980:00|82
FirePro W5100 (FireGL V)|81
Radeon E8870|81
Radeon HD 7750 Series|81
Radeon HD 7850 / R7 265 / R9 270 1024SP|81
FirePro\u2122 W4190M|80
Radeon HD 5770|80
Radeon(TM) R7 360 Series|80
FirePro M5100 FireGL V|80
Radeon RX 470/480/580|80
Radeon(TM) RX 460 Graphics|79
Radeon HD 6700 Series|79
Mobility Radeon HD 5870|79
Radeon R9 255|79
Radeon 535 Series|79
Radeon R9 M380 OpenGL Engine|78
Radeon(TM) RX 550|78
Radeon R9 M380|78
Radeon R7 250X|78
Saphire Radeon RX 580|78
Radeong 0.4 on AMD BONAIRE (DRM 2.43.0, LLVM 3.8.0)|78
Radeon HD 5000|78
Radeon HD 5770|77
Radeon RX 460|77
FirePro W4300|77
Radeon 530 Series|77
Radeon(TM) 540X|77
Radeon R9 M370X OpenGL Engine|77
FirePro V5900 (FireGL V)|77
Radeon Pro WX 4100|77
SAPPHIRE HD 5770|77
Radeon Pro WX 3100|76
FirePro W5100|76
Radeon(TM) Pro Graphics|76
Radeon Pro WX 3100|76
67FF:C8|76
Radeon(TM) HD8970M|76
Firepro M5100|76
Radeon(TM) R9 M375X|75
Radeon 550X Series|75
Radeon R9 M390|75
Radeon(TM) Vega 9 Graphics|75
FirePro V5900 (FireGL V) Graphics Adapter|74
Radeon HD 8570|74
Radeon(TM) RX 475M|74
Radeon HD 6770|74
Radeon RX 550 Series|74
Radeon RX 550|74
FirePro M4000|74
Radeon RX 460/560D / Pro 450/455/460/560|74
Radeon Pro 560|74
Radeon Vega Series / Radeon Vega Mobile Series|74
Radeon Pro 455|74
Radeon HD 7870M Series|74
Radeon(TM) R7 430|74
Radeon 620 Series|73
Radeon HD 7770 GHz Edition|73
Radeon HD 7770|73
Radeon(TM) R9 360 Series|73
Radeon HD 7770/8760 / R7 250X|73
Radeon(TM) 530|73
15DD Graphics|73
Radeon RX Vega M GL Graphics|73
Radeon(TM) R9 380|72
Radeon(TM) 530 series|72
Radeon R7 200 Series|72
Embedded Radeon E9171|72
Radeon Pro WX3200 Graphics|71
Radeon HD 8800M Series|71
Radeon R9 M375|70
Radeon HD 5770|70
Radeon Pro 555|70
Radeon R7 250E|70
Radeon HD 7750|70
Radeon Pro 555X|70
Radeon(TM) Vega 8 Mobile Graphics|70
Radeon(TM) R9 M380|69
Radeon R7 260X/360|69
Barco MXRT 7600 (WDDM)|69
Radeon(TM) Vega 10 Graphics|69
Radeon HD 7750|69
Radeon R9 M370X|69
Radeon(TM) R2E Graphics|69
Radeon R9\u2122 M370X|68
FirePro V4900 (FireGL V)|68
Radeon(TM) RX Vega11 Graphics|68
Radeon HD 5770|68
Radeon(TM) Renoir Graphics D1|68
Radeon HD 7600 Series|67
Radeon R5 340|67
Radeon(TM) Vega 9 Graphics|67
FirePro W4100 (FireGL V) Graphics Adapter|67
694E:C0|67
694C:C0|67
Radeon R7 250|66
Radeon HD 6750|66
RAVEN (DRM 3.36.0, 5.6.5-AMD, LLVM 9.0.1)|66
FirePro W600|66
Radeon R9 255|66
Radeon RX 470|66
Radeon(TM) R7 250|66
FirePro V5900|65
Radeon(TM) 530|65
Radeon Pro WX Vega M GL Graphics|65
Radeon RX 470/480|65
Radeon HD 5750|65
Radeon R7 260X|65
FirePro V5900 (FireGL V) Graphics Adapter|65
FirePro W4100 Graphics Adapter|65
Radeon HD 6700 Green Edition|65
Radeon R9 M370X|65
Radeon(TM) R7 350X|64
Radeon(TM) R7 350X|64
Radeon HD 7670|64
Radeon R9 M200X Series|64
Radeon R9 M370X|64
Radeon HD 6670|63
Radeon(TM) HD 8350|63
Radeon 530X Series|63
Radeon(TM) R9 360|63
Radeon(TM) Pro WX 4150 Graphics|63
67EF:C5|63
Radeon R7 Graphics + R5 340 Dual Graphics|62
Radeon HD 5670|62
Radeon RX 470/570|62
Radeon 530 Series|62
Radeon R7 250 Series|62
Radeon R7 430|62
Radeon HD 6750 Graphics|62
Radeon(TM) R9 M385X|62
Radeon(TM) Vega 10 Mobile Graphics|62
FirePro V5900 (FireGL V)|61
FirePro V5800 (FireGL V)|61
Radeon(TM) Vega 8 Graphics|61
FirePro V4800 (FireGL V)|61
Radeon HD 7600 Series|61
Radeon(TM) Vega 6 Graphics|61
Radeon(TM) R9 200 Series|61
Radeon HD 8850M|61
Radeon RX460|61
Radeon R7 M460|61
Radeon RX 640 Series|60
Radeon 530|60
Radeon HD 5600/5700|60
Radeon HD 5750 Series|60
Radeon R7 Graphics + R7 200 Dual Graphics|60
Radeon R7 450|60
FirePro V4900|60
Firepro W6150M|60
ASUS R7 250 Series|60
Radeon(TM) RX 560 Graphics|60
Radeon(TM) R7 M370|59
FirePro M4000 Mobility Pro Graphics|59
Radeon R5 430|59
Radeon R9 M275X|59
FirePro V5800 (FireGL) Graphics Adapter|59
Mobility Radeon HD 5870|59
Radeon(TM) R9 M385X|58
Radeon HD 7750M|58
Radeon HD 5670|58
Radeon HD 8850M|58
Radeon HD 7700M Series|58
Radeon HD 8670D + R7 200 Dual Graphics|58
Radeon R7 Series / HD 9000 Series|57
Radeon HD 6730M/6770M|57
Radeon(TM) 625|57
Radeon(TM) R9 M385|57
Radeon HD 5870M|56
Radeon 610 Series|56
FirePro W4100|56
FirePro M6000 Mobility Pro Graphics|56
Radeon RX 540 Series|56
Radeon R7 240|56
Radeon HD 7560D + HD 7700 Dual Graphics|56
Radeon R9 M370X (Bootcamp XG edition by bootcampdrivers.com)|56
FirePro V4900 (ATI FireGL)|55
Radeon(TM) R7 M350|55
FirePro M6000 Mobility Pro Graphics|55
67FF:08|55
Radeon HD 5750|55
Radeon HD 7570|55
Radeon(TM) Vega 11 Graphics|55
Radeon R7 M460|55
Radeon HD 5750 OpenGL Engine|55
Radeon(TM) R7 M370|55
Radeon HD 6730M/6770M/7690M XT|55
Radeon E8860|55
Radeon HD 8790M|54
Radeon HD 6770M|54
Radeon R7 M440|54
Radeon(TM) R7 350|54
Radeon(TM) R7 350X|54
Radeon HD 7870 XT|54
Radeon HD 7800M Series|54
Radeon 520|54
Radeon R7 M370|53
FirePro W4150M FireGL V|53
(ATI) FirePro M4000 (FireGL V) Mobility Pro Graphics|53
Radeon R9 M200X Series|53
Radeon HD 6700M/7700M/7900M Series|53
Radeon(TM) 620|53
Picasso|53
Radeon(TM) RX Vega 10 Graphics|53
67EF:CF|53
Radeon(TM) Vega 3 Graphics|53
Radeon R7 250|53
FirePro W4190M|53
Radeon(TM) Vega 8 Graphics|53
694C:C0|52
Radeon HD 5670 Series|52
Radeon(TM) RX Vega 11 Graphics|52
Radeon HD 6770M OpenGL Engine|52
Radeon(TM) M535DX|52
FirePro V4800 (FireGL V)|52
Radeon R7 350 Series|52
Barco MXRT 5600 (WDDM)|51
Radeon 630|51
FirePro V4900 (FireGL V)|51
FirePro V4900 (FireGL V) Graphics Adapter|51
Radeon(TM) Vega 3 Mobile Graphics|51
Radeon 535 Series|51
Radeon R7 Graphics|51
Radeon HD 5670|51
FirePro W4170M|50
Radeon HD 8700M Series|50
Radeon HD 8670 / R7 250/350|50
Picasso|50
FirePro V4800 (FireGL) Graphics Adapter|50
Mobility Radeon HD 5850|49
OPAL XT/GL (6604)|49
Radeon R5 M335|49
Matrox C900 PCIe x16|49
Radeon HD 7670|49
Radeon HD 6750M|49
Radeon(TM) 535|49
Radeon 540X Series|49
Radeon R9 M275|49
Radeon(TM) RX 640|49
Radeon HD 5700 Series|48
Radeon R5 M230 Series|48
Firepro M6100|48
Radeon(TM) R9 M375|48
Radeon R5 430|48
Radeon(TM) R7 250|47
Radeon R9 M265X|47
Radeon HD 6730M/6770M|47
Radeon HD 8670D|47
Radeon R5 340|47
Radeon 520|47
Radeon(TM) 520|47
FirePro V (FireGL V) Graphics Adapter|47
FirePro M5100 FireGL V|46
Radeon HD 6670|46
Radeon R7 M260X|46
Radeon HD 8550|46
FirePro M4150|46
Radeon HD 6670|46
Radeon HD 7700 Series|46
FirePro M4170|46
Radeon HD 7570|46
Radeon HD 8670D + HD 6670 Dual Graphics|45
699F:C1|45
Radeon R7 Graphics|45
Radeon(TM) R7 M340|45
FirePro W4170M (FireGL V)|45
Radeon(TM) HD 8500M/8700M|45
Radeon R7 M340|44
FirePro M5950|44
Radeon HD 8570D + R7 240 Dual Graphics|44
Radeon HD 6770M|44
Radeon HD 7730M|44
Radeon HD 8790M|44
Radeon HD 7750|44
Radeon HD 8690A|44
Mobility Radeon HD 5730 / 6570M|44
Radeon R9 A375|44
Radeon(TM) R8 M445DX|43
FirePro V (FireGL V) Graphics Adapter|43
Radeon HD 7750/8740 / R7 250E|43
FirePro V3900|43
Radeon HD 7600A Series|43
Radeon(TM) R7 200 Series Graphics|43
Radeon R7 Graphics|43
Radeon HD 6770M|43
Radeon R7 M260 Series|43
Radeon R7 M360|43
Radeon HD 8970M|43
Radeon(TM) Vega 6 Graphics|43
Radeon HD 8570|42
Radeon R7 M440|42
Radeon HD 8670A/8670M/8750M|42
Mobility Radeon HD 5850|42
Radeon HD 8750M|42
Embedded Radeon E9173|42
Radeon(TM) R7 M440|42
Radeon HD 8730M|42
Radeon R7 240 + HD 8570D Dual Graphics|42
FirePro V3900|42
Radeon(TM) 535DX|42
Radeon(TM) 520|42
Radeon(TM) Vega 8 Mobile Graphics|42
Radeon(TM) Vega 8 Graphics|42
Radeon(TM) Vega 2 Graphics|42
Radeon(TM) R9 M375|42
Radeon(TM) R8 M445DX|41
Radeon HD 6750M|41
RadeonT 540X|41
Radeon(TM) 530|41
Radeon HD 7560D + HD 6670 Dual Graphics|41
Radeon R7 240|41
Radeon(TM) R7 M360|41
Radeon R9 M280X|41
Radeon HD 7520G + HD 7600M Dual Graphics|41
Radeon(TM) R7 M445|41
Radeon Vega 8 Mobile|40
Radeon(TM) R9 255|40
Radeon R7 M260X|40
Radeon R8 M535DX|40
Radeon R7 240/340|40
Radeon(TM) R9 M375|40
Radeon(TM) R7 Graphics|40
Radeon(TM) R5 M420|40
Radeon HD 6750M|40
Radeon R9 M265X|40
Radeon R7 M340|40
Radeon HD 6570|40
Radeon HD 7500/7600 Series|39
Radeon R7 430|39
FirePro W2100|39
Radeon HD 7730M|39
Radeon HD 8670D|39
Radeon R5 M255|39
Radeon HD 7560D + HD 6570 Dual Graphics|39
Radeon RX Vega|39
Radeon R7 240 Series|39
Radeon(TM) R7 M445|39
Radeon HD 6800M Series|39
Radeon HD 8690M|39
Radeon HD 7660D + HD 6570 Dual Graphics|39
Radeon R7 M370|39
Radeon(TM) HD 6650M|38
Radeon R5 M435|38
Radeon HD 6500 Series|38
Radeon R7 Graphics|38
FirePro M7820|38
Radeon(TM) R8 M445DX Graphics|38
Radeon HD 5570|38
Radeon HD 8650G + 8750M Dual Graphics|38
Radeon HD 8670A/8670M/8750M|38
Radeon HD 6650M|38
Radeon R7 M260 Series|38
Radeon HD 7660G + 7600M Dual Graphics|38
Radeon HD 7600M Series|38
Radeon HD 7670M|37
Radeon. HD 7670M|37
Radeon(TM) R7 M265|37
Mobility Radeon HD 5000|37
Radeon HD 7500M/7600M Series|37
Radeon R5/R6/R7 Graphics|37
Radeon R7 M270|37
Radeon HD 8650G + HD 7600M Dual Graphics|37
Firepro M5100|37
Radeon HD 7730M|37
Radeon HD 8570D|37
Radeon(TM) HD 7650A Graphics|37
Radeon R7 Graphics|37
Radeon(TM) RX Vega 10 Graphics|37
Radeon HD 7600A Series|36
Radeon R7 M270|36
Radeon HD 7660D + HD 6670 Dual Graphics|36
Radeon HD 7570M/HD 7670M Graphics|36
Radeon 6600M and 6700M Series|36
Radeon R7 Graphics + R7 200 Dual Graphics|36
Radeon HD 7570 Series|36
Radeon HD 8750M|36
Radeon HD 6550D|36
FirePro M5950|36
Radeon HD 7660G + 7600M Dual Graphics|36
Radeon HD 6550D|36
Radeon HD 7600M/7700M Series|36
Radeon(TM) Vega 3 Graphics|36
Radeon(TM) 625|36
Mobility Radeon HD 5570|36
Radeon HD8730|36
Radeon(TM) R9 M380|36
Radeon(TM) R5 240|36
Radeon HD 7650M|35
Radeon HD 7560D|35
Radeon HD 8690M|35
Radeon HD 8650G + 8750M Dual Graphics|35
Radeon HD 8650G + HD 8750M Dual Graphics|35
Radeon HD 8650G + HD 8570M Dual Graphics|35
Radeon HD 6570|35
Radeon HD 7650M|35
Radeon HD 6630M/6650M/6750M/7670M/7690M|35
Radeon HD 6500 Series|35
Radeon(TM) 520|35
Radeon HD 8570D|35
Radeon HD 7600M Series|35
Radeon R7 Graphics|35
Radeon HD 7660G + 8670M Dual Graphics|35
Radeon R7 200 Series|35
Radeon HD 6630M/6650M/6750M/7670M/7690M|35
Radeon R7 M265|35
Radeon HD 8650G + HD 8750M Dual Graphics|35
Radeon HD 8650G + 8670M Dual Graphics|35
Radeon R7 Graphics|34
Radeon HD 6630M Series|34
Radeon(TM) 520|34
Radeon HD 7660D|34
ASUS R7 240 Series|34
Radeon R9 M280X|34
Radeon(TM) R5 340|34
Radeon HD 8550G + 8600/8700M Dual Graphics|34
Radeon R7 Graphics|34
Radeon(TM) HD 8500M/8700M|34
Radeon HD 7660G + HD 7600M Dual Graphics|34
Radeon HD 7670M|34
Radeon(TM) R5 M430|34
Radeon HD 8650G + 8500M Dual Graphics|34
Radeon(TM) R5 340X|34
Radeon(TM) R5 230 series|34
Radeon HD 8550|34
FirePro W2100 (FireGL V)|34
Firepro M4100 FireGL V|34
Radeon HD 6550D|34
Radeon HD 6630M|34
Radeon(TM) R9 M375|34
Radeon HD 5670 OpenGL Engine|33
Radeon HD 5670|33
Radeon R7 Graphics|33
Radeon HD 7660G|33
Radeon HD 5570|33
Radeon HD 7550M/7650M Graphics|33
Radeon HD 7660D|33
Radeon HD 7560D|33
Radeon HD 7560D|33
Radeon R5 M445 Series|33
Radeon R5 M315|33
Radeon HD 8570D|33
Radeon R7 M265|33
Radeon HD 7640G + HD 7500/7600 Dual Graphics|33
Radeon R7 Graphics|33
Radeon HD 8500M Series|33
Mobility Radeon HD 5000|33
Radeon(TM) R7 M360|33
Firepro M4100|33
Radeon(TM) Vega 10 Graphics|32
Radeon HD 7500M/7600M Series|32
Radeon HD 8550G + HD 8600/8700M Dual Graphics|32
Radeon HD 7660G|32
Radeon HD 7350|32
Radeon HD 8470D + HD 6450 Dual Graphics|32
Radeon R7 Graphics|32
Radeon HD 8730M|32
Radeon HD 7640G + HD 7400M Dual Graphics|32
Radeon HD 8690A|32
Radeon HD 8650G + 8600/8700M Dual Graphics|32
Radeon R7|32
Radeon(TM) Vega 11 Graphics|32
Radeon(TM) Vega 8 Graphics|32
Radeon R5 M200 Series|32
Radeon(TM) R5 M335|32
Radeon(TM) R5 M430|32
Radeon HD 8550G + HD 8570M Dual Graphics|32
Radeon HD 7650M Series|32
Radeon R7 250 Series|32
Radeon(TM) R7 M460|32
Radeon HD 6550D|32
Radeon HD 7660G + HD 7600M Dual Graphics|32
Radeon(TM) Vega 3 Graphics|32
Radeon HD 8470D|32
Radeon R8 M365DX|31
Madison [Mobility Radeon HD 5650/5750 / 6530M/6550M]|31
Radeon HD 6630M/6650M/6750M/7670M/7690M|31
Radeon R7 Graphics|31
Radeon E6760|31
Radeon R7 Graphics|31
Radeon(TM) Vega 8 Graphics|31
Radeon(TM) R5 M330|31
Radeon HD 8670A/8670M/8690M|31
Radeon R7 A360|31
Radeon HD 8650G + HD 8600M Dual Graphics|31
Radeon R5 M200 / HD 8500M Series|31
Radeon(TM) R8 M435DX|30
Radeon HD 7640G + HD 7670M Dual Graphics|30
Radeon(TM) Vega 10 Mobile Graphics|30
Radeon R7 Graphics|30
Radeon Pro 450/550|30
Radeon HD 8800M Series|30
Radeon HD 8470D|30
Radeon HD 7660D|30
Radeon HD 8610G + HD 8600M Dual Graphics|30
Radeon HD 7660G + 7670M Dual Graphics|30
Radeon(TM) Vega 8 Mobile Graphics|30
Radeon 610 Series|30
Radeon(TM) R5 M330|30
Radeon HD 7660G|30
Radeon HD 7640G|30
Radeon R8 M365DX|30
Radeon HD 8550G|29
Radeon HD 7540D|29
Radeon HD 7640G|29
Radeon HD 8650G|29
Radeon(TM) R7 Graphics|29
Radeon(TM) RX Vega 11 Graphics|29
Radeon HD 6650M|29
Radeon HD 7660G|29
Radeon 6600M and 6700M Series|29
Radeon HD 7640G + HD 7400M Dual Graphics|29
Radeon(TM) R5 340X|29
Radeon R5 435|29
Radeon HD 6500M/5600/5700 Series|29
Firepro M4100 FireGL V|29
Radeon R7 Graphics|29
Radeon(TM) 535|29
Radeon R7 240 Series|29
Radeon(TM) R7|29
Radeon HD 8550G + 8500M Dual Graphics|28
Radeon(TM) 530|28
Radeon HD 5650 Series|28
Radeon HD 7570M|28
Radeon HD 7570M|28
ASUS R7 240 Series|28
Radeon HD 6570|28
Radeon(TM) Vega 8 Graphics|28
Radeon E8860|28
Radeon(TM) 530 series|28
Radeon(TM) R5 M315|28
Radeon HD 5500 Series|28
Radeon HD 8610G + HD 8670M Dual Graphics|28
Radeon(TM) R6|28
Radeon R9 M275X|28
Radeon HD 8550G + R5 M230 Dual Graphics|28
Radeon HD 8470D|28
Radeon HD 8670D|28
Radeon HD 7620G|28
Radeon(TM) R8 M350DX|28
Radeon HD 8470D|27
Radeon(TM) R8 M445DX|27
Radeon(TM) R7 Graphics|27
Radeon(TM) R5 Graphics|27
Radeon(TM) R7 M340|27
Radeon(TM) R6 Graphics|27
Radeon R6 Graphics|27
Radeon R5 M230 Series|27
Radeon HD 8650G|27
Radeon HD 7480D|27
Radeon(TM) R8 M445DX Graphics|27
Radeon(TM) R6 Graphics|27
Radeon R7 Graphics|27
Radeon R6|27
Radeon R5 M255|27
Radeon(TM) Vega 3 Graphics|27
Radeon 550X|27
Radeon(TM) Vega 3 Graphics|27
Radeon HD 7500/7600 Series|27
Radeon HD 8650G|27
Radeon HD 5500 Series|27
Radeon HD 7610M|27
Radeon Instinct MI25 MxGPU|27
Radeon(TM) HD8530M|27
Radeon R7 M260|27
Radeon(TM) R8 M445DX|27
Radeon R7 Graphics|26
Radeon HD 8500M|26
Radeon(TM) R7 M260DX|26
Radeon HD 8410G|26
Radeon HD 8670A/8670M/8690M|26
Radeon(TM) R7 M360|26
Radeon(TM) R7 M360|26
Radeon HD 8670D|26
Radeon R9 M275|26
Radeon HD 7640G|26
Radeon(TM) R7 Graphics|26
MxGPU|26
Radeon HD 8370D|26
Radeon HD 6620G|25
Radeon HD 7560D|25
Radeon HD 8570 / R5 430 / R7 240/340 / Radeon 520|25
Radeon R4 Graphics|25
Radeon R6 Graphics|25
Radeon R7 Graphics|25
Radeon(TM) 535DX|25
Radeon(TM) 540 Graphics|25
Radeon(TM) R5 M330|25
Radeon HD 6530D|25
Radeon R6 Graphics|25
Radeon HD 8510G|25
Radeon HD 6620G|25
Radeon R7 M360|24
Radeon(TM) R6 Graphics|24
Radeon R7 M260|24
Radeon HD 8610G + HD 8600M Dual Graphics|24
Radeon(TM) R6 Graphics|24
Radeon R5 M200 / HD 8500M Series|24
Radeon R7 Graphics|24
Radeon HD 7600G|24
Radeon R7 Graphics|24
Radeon HD 6620G|24
Radeon R5 M330|24
Radeon(TM) R5 240|24
Radeon(TM) HD 6620G|24
FirePro V3800 (FireGL V)|24
Radeon HD 6520G|24
Radeon R7 Graphics|24
Radeon HD 7520G|24
Radeon(TM) R6 Graphics|24
Radeon(TM) R7 M260|24
Radeon RX 540 Series|24
Radeon(TM) R5 M320|24
Radeon HD 8500M|23
Radeon R5 M230|23
Radeon HD 8670M|23
Radeon HD 8550G + HD 8750M Dual Graphics|23
Radeon HD 8600M Series (HAINAN, DRM 3.40.0, 5.11.13-arch1-1, LLVM 11.1.0)|23
Radeon HD 8550G|23
Radeon R5 M240|23
Radeon R5 M240 Series|23
Radeon HD 7540D|23
Radeon(TM) R5 M430|23
Radeon R5 Graphics|23
Radeon(TM) R5 M430|23
Radeon R6 Graphics|23
Radeon HD 7520G|23
Radeon R7 Graphics|23
Radeon HD 8610G|22
FirePro 3800 (FireGL) Graphics Adapter|22
Radeon HD 7570M/HD 7670M Graphics|22
Radeon HD 7480D|22
Radeon(TM) R7 Graphics|22
Radeon HD 8650G + HD 8600M Dual Graphics|22
Radeon(TM) Vega 6 Graphics|22
Radeon R7 Graphics|22
Radeon R5 Graphics|22
Radeon HD 7660G + HD 8600M Dual Graphics|22
FirePro M2000|22
Radeon R7 Graphics|22
Radeon HD 7870M|22
Radeon R5 M335|22
Radeon R5|22
Radeon HD 8500M Series|22
Radeon(TM) HD 8490|22
Radeon HD 8670M|22
Radeon HD 7660G + HD 7670M Dual Graphics|22
Radeon 7500M/7600M Series|22
Radeon R5 Graphics|21
Radeon(TM) R4 Graphics|21
Radeon HD 8490|21
Radeon HD 8490|21
Radeon R7 Graphics|21
Radeon HD 8570M|21
Radeon(TM) R5 M320|21
Radeon R2|21
Radeon HD 6530D|21
Radeon(TM) HD 6470M|21
MxGPU|21
Radeon HD 7000 series|21
Radeon HD 7470|21
Radeon(TM) R8 M350DX|21
Radeon R7 Graphics|21
Radeon HD 7520G + HD 7400M Dual Graphics|21
Radeon(TM) R5 M335|21
Radeon HD 7400G|21
Radeon HD 7640G + HD 8500M Dual Graphics|21
Radeon HD 7000 series|21
Radeon(TM) R5 Graphics|20
Radeon(TM) R7 M520 (R17M-M1-30)|20
Radeon HD 8470|20
Radeon HD 7480D|20
Radeon HD 6400M/7400M Series|20
Radeon(TM) R3 Graphics|20
Radeon R6 M255DX|20
Radeon HD 8370D|20
Radeon R5 Graphics|20
Radeon R7 Graphics|20
Radeon HD 6410D|20
Radeon(TM) R5 Graphics|20
Radeon R5 M330|20
Radeon R7 M260DX|20
Radeon(TM) R5 Graphics|20
Radeon HD 7480D|20
Radeon HD 6470M|20
Radeon Hybrid (Blocked)|20
Radeon(TM) R7 Graphics|20
Radeon(TM) R6 M340DX|20
Radeon R5 235|20
Radeon HD 7520G|19
Radeon(TM) R6 M255DX|19
Radeon R5 M240|19
Radeon(TM) R3 Graphics|19
Radeon R7E Graphics|19
Radeon R5 M200 Series|19
Radeon HD 7470|19
Radeon HD 7640G + 8500M Dual Graphics|19
Radeon(TM) R5 M330|19
Radeon HD 6470M|19
Radeon R3 Graphics|19
Radeon HD 8400E|19
Radeon HD 7640G + HD 8570M Dual Graphics|19
Radeon HD 8400|19
Radeon HD 8400 / R3 Series|19
Radeon R5 Graphics|19
Radeon(TM) R7 M265|19
Radeon R5 M230|19
Radeon R5 Graphics|19
Radeon HD 7620G|19
Radeon R5 Graphics|19
Radeon(TM) HD 6470M|19
Radeon HD 7480D|18
Radeon R7 Graphics|18
Radeon(TM) R5 Graphics|18
Radeon HD 8550G|18
Radeon HD 8370D|18
Radeon R5 Graphics|18
Radeon(TM) HD 7450|18
Radeon HD 6530D|18
Radeon HD 8570M|18
Radeon R6 Graphics|18
Radeon HD 7650A|18
Radeon HD 8450G|18
Radeon HD 8550G + R5 M230 Dual Graphics|18
Radeon HD 7640G + 7470M Dual Graphics|18
Radeon HD 8370D|18
Radeon HD 7400M Series|18
Radeon HD 8670D + R5 200 Dual Graphics|17
Radeon HD 7500G|17
Radeon HD 7790|17
Radeon HD 7450M|17
Radeon(TM) HD 7450A Graphics|17
Radeon(TM) R5 Graphics|17
Radeon(TM) R6 Graphics|17
Radeon(TM) R4 Graphics|17
Radeon HD 8650G + HD 8500M Dual Graphics|17
Radeon HD 7400M Series|17
Radeon HD 8450G|17
Radeon HD 6520G|17
Radeon HD 8470D|17
Radeon(TM) R5 Graphics|17
Radeon(TM) R4E Graphics|17
Radeon HD 8330|17
Radeon HD 8400|17
Radeon(TM) HD 8510G|17
Radeon(TM) R5 Graphics|17
Radeon HD 8650G|17
Radeon HD 6490M|17
Radeon R7 Graphics|16
Radeon HD 6400 Series|16
Radeon HD 8510G|16
Radeon HD 7400 Series|16
Radeon HD 7400 Series|16
Radeon(TM) HD 8510G|16
Radeon HD 6370D|16
Radeon HD 7420G|16
Radeon HD 7520G + HD 7600M Dual Graphics|16
Radeon R9 260|16
Radeon HD 7640G + 7600M Dual Graphics|16
Radeon HD 7470M|16
Radeon(TM) R2 Graphics|16
RADEON HD 6450|16
Radeon(TM) R1E Graphics|16
Radeon R5 Graphics|16
Radeon HD 7420G|16
Radeon(TM) R4 Graphics|16
Radeon(TM) R4 Graphics|16
Radeon(TM) R4 Graphics|16
Radeon HD 7480D|16
Radeon HD 6490M|15
RADEON HD 6450|15
Radeon(TM) HD 8610G|15
Radeon(TM) HD 8610G|15
Radeon HD 8610G + 8600M Dual Graphics|15
Radeon HD 7350|15
Radeon(TM) HD 6480G|15
Radeon HD 8650G + 8600M Dual Graphics|15
Radeon HD 8570D|15
Radeon HD 6370M|15
Mobility Radeon HD 5000 Series|15
Radeon R2 Graphics|15
Radeon HD 8240 / R3 Series|15
Radeon HD 8650G + R5 M200 Dual Graphics|15
Radeon HD 8400E|15
Radeon(TM) R4 Graphics|15
Radeon R5 Graphics|15
Radeon HD 8610G|15
Radeon HD 8650G + HD 8500M Dual Graphics|15
Radeon(TM) R7 M260|15
ASUS EAH6450 Series|15
Radeon R3 Graphics|15
Radeon(TM) R6 M340DX|15
Radeon R6E Graphics|15
Radeon R5 Graphics|15
Radeon R2 Series|14
Radeon HD 6450/7450/8450/R5 230|14
Radeon HD 8200 / R3 Series|14
Radeon(TM) R3 Graphics|14
Radeon R5 230|14
Radeon(TM) HD 8510G|14
Radeon(TM) R4 Graphics|14
Radeon R5 M435|14
Radeon HD 8240|14
ASUS R5 230 Series|14
FirePro M2000|14
Radeon HD 7500G|14
Radeon HD 7450|14
RADEON HD 6450|14
Radeon HD 8400E|14
RADEON HD 6350|14
Radeon HD 6480G|14
Radeon(TM) R5E Graphics|14
CARRIZO 9874|14
Mobility Radeon HD 5000 Series|14
Radeon HD 6630M|14
Radeon HD 6370M|14
Radeon HD 8400 / R3 Series|14
Radeon(TM) R2 Graphics|14
ASUS EAH6450 Series|14
Radeon HD 7470M|13
Mobility Radeon HD 5470|13
Mobility Radeon HD 5400 Series|13
Radeon(TM) R5E Graphics|13
Radeon(TM) R2 Graphics|13
Radeon HD 6540|13
Radeon HD 7450|13
Radeon HD 5450|13
Radeon HD 8600M Series|13
Radeon HD 8400 / R3 Series|13
Kaveri|13
Radeon(TM) HD 6480G|13
Radeon HD 5400 Series|13
Radeon HD 8330|13
RADEON HD 6350|13
Radeon R4/R5 Graphics|13
Radeon HD 7600G +\u2122 HD Dual Graphics|13
Radeon R3 Graphics|13
ASUS R5 230 Series|13
Radeon(TM) R7 Graphics|13
Radeon HD 7620G|13
Radeon HD 8250|13
Radeon(TM) R7 Graphics|12
Radeon HD 6450/7450/8450 / R5 230|12
Radeon HD 6480G|12
Radeon(TM) R7 Graphics|12
Radeon HD 5450 Series|12
Radeon HD 8400 / R3 Series|12
Radeon(TM) HD 6400 Series|12
Radeon(TM) R4 Graphics|12
RADEON HD5450|12
Radeon R5 Graphics|12
Radeon R5 Graphics|12
Radeon(TM) R6 Graphics|12
Radeon(TM) R4 Graphics|12
Radeon(TM) R2 Graphics|12
Radeon HD 8210|12
Radeon R5 230|12
Radeon R3 Graphics|12
FirePro 2270|12
Radeon(TM) R2E Graphics|12
Radeon HD 8400 / R3 Series|12
Radeon HD 8350G|12
Radeon HD 8400|12
Radeon R2 Graphics|12
Radeon HD 8210 Graphics|12
Radeon E6460|12
Radeon(TM) HD 8280E|12
Radeon R2 Graphics|11
Radeon HD 8450G + HD 8750M Dual Graphics|11
Radeon HD 8330|11
Radeon HD 5470|11
Radeon HD 7600G + 7500M/7600M Dual Graphics|11
Radeon R5 220|11
Radeon HD 8200 / R3 Series|11
Radeon HD 8240|11
Radeon HD 8400 / R3 Series|11
Radeon HD 8200 / R3 Series|11
Radeon HD 5450|11
Radeon(TM) 620|11
Radeon(TM) Vega 8 Mobile Graphics|11
Radeon HD 6530D|11
Radeon(TM) HD 6520G|11
Radeon HD 6300M Series|11
ASUS EAH5450|11
Radeon R5 220|11
Radeon HD 8250|11
Radeon HD 7340|11
Radeon HD 7340M|11
Radeon HD 8210|11
Radeon HD 7700 Series|10
Radeon HD 6380G|10
Radeon HD 5400 Series|10
Radeon HD 8240|10
Radeon HD 7640G + 7670M Dual Graphics|10
Radeon(TM) R6 Graphics|10
ASUS EAH5450 Series|10
Radeon HD 6320|10
Radeon HD 7340G|10
Radeon HD 6410D|10
Radeon HD 7340|10
Radeon HD 6320|10
Radeon(TM) R2 Graphics|10
Radeon HD 8180|9
Mobility Radeon HD 5430|9
Radeon R2 Graphics|9
Radeon R2 Series|9
Radeon HD 8210|9
FirePro 2270|9
Radeon R2E Graphics|9
Radeon HD 7340|9
Radeon HD 6320|9
Radeon HD 7310|9
Radeon HD 6310|9
Radeon R7 Graphics|9
Radeon HD 7310|8
Radeon HD 8250|8
Radeon HD 8180|8
Radeon HD 6630M|8
Radeon HD 6230|8
Radeon HD 6320|8
Radeon HD 6400M Series|8
Radeon HD 7290 Graphics|7
Radeon HD 6290|7
Radeon HD 6310|7
Radeon HD 8180|7
ASUS EAH5450 Series|7
Radeon(TM) R2 Graphics|6
Radeon HD 6310|6
Radeon HD 7500G|6
Radeon HD 8240 / R3 Series|6
Radeon HD 6250|6
Radeon HD 6380G|6
Radeon HD 6300M Series|5
Radeon HD 7310|5
Radeon R3 Graphics|5
Radeon(TM) R6 Graphics|5
Radeon HD 6250|5
Radeon HD 6290|5
Radeon HD 6250|5
Radeon HD 7290 Graphics|4
Radeon HD 5000/6000/7350/8350 Series|3
Radeon RX Vega 56 OpenGL Engine|-1
FirePro V4800 (FireGL) Graphics Adapter|-1
Radeon HD 7670M|-1
Radeon HD 8570D|-1
7340:C5|-1
Radeon HD 8550G|-1
Radeon R5 Graphics|-1
ASUS R7 360 Series|-1
Bonaire [FirePro W5100]|-1
Radeon HD 6380G|-1
Radeon R7 Graphics|-1
FireGL V8650|-1
FirePro S7150|-1
FirePro V3900 (FireGL V)|-1
FirePro V7800 (FireGL V)|-1
FirePro W4100 Graphics Adapter|-1
FirePro W4170M (FireGL V)|-1
Gigabyte Radeon RX 580|-1
Mobility FireGL V5700|-1
Mobility Radeon 4100|-1
Mobility Radeon HD 2400|-1
Mobility Radeon HD 2400 XT|-1
Mobility Radeon HD 2600|-1
Mobility Radeon HD 2600 XT|-1
Mobility Radeon HD 3200|-1
Mobility Radeon HD 3400 Series|-1
Mobility Radeon HD 3430|-1
Mobility Radeon HD 3470|-1
Mobility Radeon HD 3650|-1
Mobility Radeon HD 4200 Series|-1
Mobility Radeon HD 4250|-1
Mobility Radeon HD 4300 Series|-1
Mobility Radeon HD 4500 Series|-1
Mobility Radeon HD 4500/5100 Series|-1
Mobility Radeon HD 4650|-1
Mobility Radeon HD 4670|-1
Mobility Radeon HD 4850|-1
R9 270X Devil|-1
RX 560X|-1
Radeon|-1
Radeon(TM) HD8530M|-1
Radeon 3000|-1
Radeon 3100 Graphics|-1
Radeon HD 2400 PRO|-1
Radeon HD 2400 XT|-1
Radeon HD 2600 Pro|-1
Radeon HD 2600 XT|-1
Radeon HD 2900 GT|-1
Radeon HD 3200 Graphics|-1
Radeon HD 3300|-1
Radeon HD 3450|-1
Radeon HD 3470|-1
Radeon HD 3600 Series|-1
Radeon HD 3650|-1
Radeon HD 3850|-1
Radeon HD 3870|-1
Radeon HD 3870 X2|-1
Radeon HD 4200|-1
Radeon HD 4250|-1
Radeon HD 4290|-1
Radeon HD 4300/4500 Series|-1
Radeon HD 4550|-1
Radeon HD 4600 Series|-1
Radeon HD 4650|-1
Radeon HD 4670|-1
Radeon HD 4830|-1
Radeon HD 4850|-1
Radeon HD 4870|-1
Radeon HD 4890|-1
Radeon HD 5670 640SP Edition|-1
Radeon HD 5800 Series|-1
Radeon HD 5850|-1
Radeon HD 6490M|-1
Radeon HD 6730M/6770M|-1
Radeon HD 6750|-1
Radeon HD 6800M Series|-1
Radeon HD 7540D + HD 6670 Dual Graphics|-1
Radeon HD 7700M Series|-1
Radeon HD 7800 Series|-1
Radeon HD 8350|-1
Radeon HD 8370D|-1
Radeon HD 8600/8700M|-1
Radeon Pro WX Vega M GL Graphics|-1
Radeon R5 200 Series|-1
Radeon R7 A370|-1
Radeon R9 200 Series|-1
Radeon R9 290X/390X|-1
Radeon R9 380X|-1
Radeon RX 480|-1
Radeon RX 550X|-1
Radeon RX 6650M|-1
Radeon RX6600XT|-1
Radeon(TM) R8 M435DX|-1
Radeon(TM) R9 290X|-1
Radeon(TM) RX540|-1
inc. Radeon HD 7970|-1
Radeong 0.4 on AMD CAPE VERDE (DRM 2.43.0, LLVM 3.7.0)|-1
Radeong 0.4 on AMD CAPE VERDE (DRM 3.9.0 / 4.9.0-rc1+, LLVM 4.0.0)|-1
Radeong 0.4 on AMD FIJI (DRM 3.2.0 / 4.7.0-rc5+, LLVM 4.0.0)|-1
Radeong 0.4 on AMD TAHITI (DRM 2.43.0, LLVM 3.9.0)|-1
`;function t(){return a}},795777:function(e,n,o){"use strict";o.d(n,{I:function(){return c}});var a=o(444313),t=o(984639),r=o(521917),i=o(640878),d=o(113269),s=o(37586),R=o(707476),l=o(29730),c=function(e){(0,i.Z)(o,e);var n=(0,d.Z)(o);function o(){var e;(0,a.Z)(this,o);for(var t=arguments.length,i=Array(t),d=0;d<t;d++)i[d]=arguments[d];return e=n.call.apply(n,[this].concat(i)),(0,s.Z)((0,r.Z)(e),"priority",80),(0,s.Z)((0,r.Z)(e),"incompatibleTokens",["a","b","t","T"]),e}return(0,t.Z)(o,[{key:"parse",value:function(e,n,o){switch(n){case"B":case"BB":case"BBB":return o.dayPeriod(e,{width:"abbreviated",context:"formatting"})||o.dayPeriod(e,{width:"narrow",context:"formatting"});case"BBBBB":return o.dayPeriod(e,{width:"narrow",context:"formatting"});default:return o.dayPeriod(e,{width:"wide",context:"formatting"})||o.dayPeriod(e,{width:"abbreviated",context:"formatting"})||o.dayPeriod(e,{width:"narrow",context:"formatting"})}}},{key:"set",value:function(e,n,o){return e.setUTCHours((0,l.RQ)(o),0,0,0),e}}]),o}(R._)},936908:function(e,n,o){"use strict";o.d(n,{v:function(){return u}});var a=o(444313),t=o(984639),r=o(521917),i=o(640878),d=o(113269),s=o(37586),R=o(707476),l=o(29730),c=o(786830),u=function(e){(0,i.Z)(o,e);var n=(0,d.Z)(o);function o(){var e;(0,a.Z)(this,o);for(var t=arguments.length,i=Array(t),d=0;d<t;d++)i[d]=arguments[d];return e=n.call.apply(n,[this].concat(i)),(0,s.Z)((0,r.Z)(e),"priority",130),(0,s.Z)((0,r.Z)(e),"incompatibleTokens",["G","y","Y","u","Q","q","M","L","w","d","D","e","c","t","T"]),e}return(0,t.Z)(o,[{key:"parse",value:function(e,n){return"R"===n?(0,l.Db)(4,e):(0,l.Db)(n.length,e)}},{key:"set",value:function(e,n,o){var a=new Date(0);return a.setUTCFullYear(o,0,4),a.setUTCHours(0,0,0,0),(0,c.Z)(a)}}]),o}(R._)},114842:function(e,n,o){"use strict";o.d(n,{q:function(){return c}});var a=o(444313),t=o(984639),r=o(521917),i=o(640878),d=o(113269),s=o(37586),R=o(707476),l=o(29730),c=function(e){(0,i.Z)(o,e);var n=(0,d.Z)(o);function o(){var e;(0,a.Z)(this,o);for(var t=arguments.length,i=Array(t),d=0;d<t;d++)i[d]=arguments[d];return e=n.call.apply(n,[this].concat(i)),(0,s.Z)((0,r.Z)(e),"priority",130),(0,s.Z)((0,r.Z)(e),"incompatibleTokens",["Y","R","u","w","I","i","e","c","t","T"]),e}return(0,t.Z)(o,[{key:"parse",value:function(e,n,o){var a=function(e){return{year:e,isTwoDigitYear:"yy"===n}};switch(n){case"y":return(0,l.jg)((0,l.ZL)(4,e),a);case"yo":return(0,l.jg)(o.ordinalNumber(e,{unit:"year"}),a);default:return(0,l.jg)((0,l.ZL)(n.length,e),a)}}},{key:"validate",value:function(e,n){return n.isTwoDigitYear||n.year>0}},{key:"set",value:function(e,n,o){var a=e.getUTCFullYear();if(o.isTwoDigitYear){var t=(0,l.WG)(o.year,a);return e.setUTCFullYear(t,0,1),e.setUTCHours(0,0,0,0),e}var r="era"in n&&1!==n.era?1-o.year:o.year;return e.setUTCFullYear(r,0,1),e.setUTCHours(0,0,0,0),e}}]),o}(R._)},844402:function(e,n,o){"use strict";var a=o(716997).default;Object.defineProperty(n,"__esModule",{value:!0}),n.default=void 0;var t=a(o(204197)),r={ordinalNumber:function(e,n){var o=Number(e),a=o%100;if(a>20||a<10)switch(a%10){case 1:return o+"st";case 2:return o+"nd";case 3:return o+"rd"}return o+"th"},era:(0,t.default)({values:{narrow:["B","A"],abbreviated:["BC","AD"],wide:["Before Christ","Anno Domini"]},defaultWidth:"wide"}),quarter:(0,t.default)({values:{narrow:["1","2","3","4"],abbreviated:["Q1","Q2","Q3","Q4"],wide:["1st quarter","2nd quarter","3rd quarter","4th quarter"]},defaultWidth:"wide",argumentCallback:function(e){return e-1}}),month:(0,t.default)({values:{narrow:["J","F","M","A","M","J","J","A","S","O","N","D"],abbreviated:["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],wide:["January","February","March","April","May","June","July","August","September","October","November","December"]},defaultWidth:"wide"}),day:(0,t.default)({values:{narrow:["S","M","T","W","T","F","S"],short:["Su","Mo","Tu","We","Th","Fr","Sa"],abbreviated:["Sun","Mon","Tue","Wed","Thu","Fri","Sat"],wide:["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]},defaultWidth:"wide"}),dayPeriod:(0,t.default)({values:{narrow:{am:"a",pm:"p",midnight:"mi",noon:"n",morning:"morning",afternoon:"afternoon",evening:"evening",night:"night"},abbreviated:{am:"AM",pm:"PM",midnight:"midnight",noon:"noon",morning:"morning",afternoon:"afternoon",evening:"evening",night:"night"},wide:{am:"a.m.",pm:"p.m.",midnight:"midnight",noon:"noon",morning:"morning",afternoon:"afternoon",evening:"evening",night:"night"}},defaultWidth:"wide",formattingValues:{narrow:{am:"a",pm:"p",midnight:"mi",noon:"n",morning:"in the morning",afternoon:"in the afternoon",evening:"in the evening",night:"at night"},abbreviated:{am:"AM",pm:"PM",midnight:"midnight",noon:"noon",morning:"in the morning",afternoon:"in the afternoon",evening:"in the evening",night:"at night"},wide:{am:"a.m.",pm:"p.m.",midnight:"midnight",noon:"noon",morning:"in the morning",afternoon:"in the afternoon",evening:"in the evening",night:"at night"}},defaultFormattingWidth:"wide"})};n.default=r,e.exports=n.default},26622:function(e,n,o){var a=o(191483),t=o(574443),r=o(155847),i=o(979585),d=o(362656);function s(e){var n=-1,o=null==e?0:e.length;for(this.clear();++n<o;){var a=e[n];this.set(a[0],a[1])}}s.prototype.clear=a,s.prototype.delete=t,s.prototype.get=r,s.prototype.has=i,s.prototype.set=d,e.exports=s},995469:function(e,n,o){var a=o(871238),t=o(601292),r=o(330301),i=o(937610),d=o(727986);e.exports=function(e,n,o,s){if(!i(e))return e;n=t(n,e);for(var R=-1,l=n.length,c=l-1,u=e;null!=u&&++R<l;){var h=d(n[R]),p=o;if("__proto__"===h||"constructor"===h||"prototype"===h)break;if(R!=c){var f=u[h];void 0===(p=s?s(f,h,u):void 0)&&(p=i(f)?f:r(n[R+1])?[]:{})}a(u,h,p),u=u[h]}return e}},635734:function(e,n,o){var a=o(911727),t=o(871343),r=o(388236),i=Object.prototype,d=Function.prototype.toString,s=i.hasOwnProperty,R=d.call(Object);e.exports=function(e){if(!r(e)||"[object Object]"!=a(e))return!1;var n=t(e);if(null===n)return!0;var o=s.call(n,"constructor")&&n.constructor;return"function"==typeof o&&o instanceof o&&d.call(o)==R}},563429:function(){!function(){if("undefined"!=typeof Prism&&"undefined"!=typeof document){var e="line-numbers",n=/\n(?!$)/g,o=Prism.plugins.lineNumbers={getLine:function(n,o){if("PRE"===n.tagName&&n.classList.contains(e)){var a=n.querySelector(".line-numbers-rows");if(a){var t=parseInt(n.getAttribute("data-start"),10)||1,r=t+(a.children.length-1);o<t&&(o=t),o>r&&(o=r);var i=o-t;return a.children[i]}}},resize:function(e){t([e])},assumeViewportIndependence:!0},a=void 0;window.addEventListener("resize",function(){o.assumeViewportIndependence&&a===window.innerWidth||(a=window.innerWidth,t(Array.prototype.slice.call(document.querySelectorAll("pre.line-numbers"))))}),Prism.hooks.add("complete",function(o){if(o.code){var a=o.element,r=a.parentNode;if(r&&/pre/i.test(r.nodeName)&&!a.querySelector(".line-numbers-rows")&&Prism.util.isActive(a,e)){a.classList.remove(e),r.classList.add(e);var i,d=o.code.match(n),s=Array((d?d.length+1:1)+1).join("<span></span>");(i=document.createElement("span")).setAttribute("aria-hidden","true"),i.className="line-numbers-rows",i.innerHTML=s,r.hasAttribute("data-start")&&(r.style.counterReset="linenumber "+(parseInt(r.getAttribute("data-start"),10)-1)),o.element.appendChild(i),t([r]),Prism.hooks.run("line-numbers",o)}}}),Prism.hooks.add("line-numbers",function(e){e.plugins=e.plugins||{},e.plugins.lineNumbers=!0})}function t(e){if(0!=(e=e.filter(function(e){var n=(e?window.getComputedStyle?getComputedStyle(e):e.currentStyle||null:null)["white-space"];return"pre-wrap"===n||"pre-line"===n})).length){var o=e.map(function(e){var o=e.querySelector("code"),a=e.querySelector(".line-numbers-rows");if(o&&a){var t=e.querySelector(".line-numbers-sizer"),r=o.textContent.split(n);t||((t=document.createElement("span")).className="line-numbers-sizer",o.appendChild(t)),t.innerHTML="0",t.style.display="block";var i=t.getBoundingClientRect().height;return t.innerHTML="",{element:e,lines:r,lineHeights:[],oneLinerHeight:i,sizer:t}}}).filter(Boolean);o.forEach(function(e){var n=e.sizer,o=e.lines,a=e.lineHeights,t=e.oneLinerHeight;a[o.length-1]=void 0,o.forEach(function(e,o){if(e&&e.length>1){var r=n.appendChild(document.createElement("span"));r.style.display="block",r.textContent=e}else a[o]=t})}),o.forEach(function(e){for(var n=e.sizer,o=e.lineHeights,a=0,t=0;t<o.length;t++)void 0===o[t]&&(o[t]=n.children[a++].getBoundingClientRect().height)}),o.forEach(function(e){var n=e.sizer,o=e.element.querySelector(".line-numbers-rows");n.style.display="none",n.innerHTML="",e.lineHeights.forEach(function(e,n){o.children[n].style.height=e+"px"})})}}}()},356297:function(e,n,o){"use strict";o.r(n)},607981:function(e,n,o){"use strict";o.r(n)},52012:function(e,n,o){"use strict";o.r(n)},688802:function(e,n,o){"use strict";o.r(n)},201394:function(e,n,o){"use strict";o.r(n)},582383:function(e,n,o){"use strict";o.d(n,{Z:function(){return c}});var a=o(977353),t=o.n(a),r=o(703196),i=o(861275),d=o.n(i),s=o(945413),R=o(794840),l=o(975867);class c extends r.Component{renderChildren(e,n){let{componentName:o}=this.props,a=e;!(null==e?void 0:e.code)&&(a=l.Z);let r=t()(l.Z,"dateFnsLocale"),i=t()(a,"dateFnsLocale",r),d=t()(a,"currency");return n(a[o],a.code,i,d)}render(){let{children:e}=this.props;return r.createElement(R.Z.Consumer,null,n=>{let{locale:o}=n;return r.createElement(s.Z.Consumer,null,n=>this.renderChildren(o||n,e))})}}c.propTypes={componentName:d().string.isRequired,children:d().any},c.defaultProps={componentName:""}},873248:function(e,n,o){"use strict";o(370483);var a=o(279142),t=o.n(a),r=o(55345),i=o.n(r),d=o(639444),s=o.n(d),R=o(703196),l=o(861275),c=o.n(l),u=o(256195),h=o.n(u),p=o(978243),f=o(9587),M=o(889287);o(522252);var D=o(271838),g=o(596861),H=o(805548),m=function(e,n){var o={};for(var a in e)Object.prototype.hasOwnProperty.call(e,a)&&0>n.indexOf(a)&&(o[a]=e[a]);if(null!=e&&"function"==typeof Object.getOwnPropertySymbols)for(var t=0,a=Object.getOwnPropertySymbols(e);t<a.length;t++)0>n.indexOf(a[t])&&Object.prototype.propertyIsEnumerable.call(e,a[t])&&(o[a[t]]=e[a[t]]);return o};class X extends D.Z{componentDidUpdate(e){this.props.checked!==e.checked&&(i()(this.props.checked)?this.foundation.setChecked(!1):t()(this.props.checked)&&this.foundation.setChecked(this.props.checked))}get adapter(){return Object.assign(Object.assign({},super.adapter),{setHover:e=>{this.setState({hover:e})},setAddonId:()=>{this.setState({addonId:(0,M.Ms)({prefix:"addon"})})},setChecked:e=>{this.setState({checked:e})},setExtraId:()=>{this.setState({extraId:(0,M.Ms)({prefix:"extra"})})},setFocusVisible:e=>{this.setState({focusVisible:e})}})}isInGroup(){return this.context&&this.context.radioGroup}focus(){this.radioEntity.focus()}blur(){this.radioEntity.blur()}render(){let e,n,o,a,t,r,i,d,s;let l=this.props,{addonClassName:c,addonStyle:u,disabled:p,style:M,className:D,prefixCls:H,displayMode:X,children:v,extra:T,mode:S,type:b,value:y,name:G}=l,P=m(l,["addonClassName","addonStyle","disabled","style","className","prefixCls","displayMode","children","extra","mode","type","value","name"]),{hover:A,addonId:x,extraId:E,focusVisible:F,checked:w}=this.state,C={checked:w,disabled:p};this.isInGroup()?(e=this.context.radioGroup.value===y,n=p||this.context.radioGroup.disabled,o=this.context.mode,a=this.context.radioGroup.isButtonRadio,t=this.context.radioGroup.isCardRadio,r=this.context.radioGroup.isPureCardRadio,d=this.context.radioGroup.buttonSize,s=H||this.context.radioGroup.prefixCls,C.checked=e,C.disabled=n):(e=w,n=p,o=S,i="button"===b,s=H,a=b===f.j2.TYPE_BUTTON,r=b===f.j2.TYPE_PURECARD,t=b===f.j2.TYPE_CARD||r);let V=void 0===a?i:a,L=s||f.Gv.PREFIX,_=t||r||V,O=h()(L,{[`${L}-disabled`]:n,[`${L}-checked`]:e,[`${L}-${X}`]:!!X,[`${L}-buttonRadioComponent`]:i,[`${L}-buttonRadioGroup`]:a,[`${L}-buttonRadioGroup-${d}`]:a&&d,[`${L}-cardRadioGroup`]:t,[`${L}-cardRadioGroup_disabled`]:n&&t,[`${L}-cardRadioGroup_checked`]:t&&e&&!n,[`${L}-cardRadioGroup_checked_disabled`]:t&&e&&n,[`${L}-cardRadioGroup_hover`]:t&&!e&&A&&!n,[D]:!!D,[`${L}-focus`]:F&&(t||r)}),k=this.isInGroup()&&this.context.radioGroup.name,I=h()({[`${L}-addon`]:!V,[`${L}-addon-buttonRadio`]:V,[`${L}-addon-buttonRadio-checked`]:V&&e,[`${L}-addon-buttonRadio-disabled`]:V&&n,[`${L}-addon-buttonRadio-hover`]:V&&!e&&!n&&A,[`${L}-addon-buttonRadio-${d}`]:V&&d,[`${L}-focus`]:F&&V},c);return R.createElement("label",Object.assign({style:M,className:O,onMouseEnter:this.handleMouseEnter,onMouseLeave:this.handleMouseLeave},this.getDataAttr(P)),R.createElement(g.Z,Object.assign({},this.props,C,{mode:o,name:null!=G?G:k,isButtonRadio:V,isPureCardRadioGroup:r,onChange:this.onChange,ref:e=>{this.radioEntity=e},addonId:v&&x,extraId:T&&E,focusInner:F&&!_,onInputFocus:this.handleFocusVisible,onInputBlur:this.handleBlur})),v||T?R.createElement("div",{className:h()([`${L}-content`,{[`${L}-isCardRadioGroup_content`]:t}])},v?R.createElement("span",{className:I,style:u,id:x,"x-semi-prop":"children"},v):null,T&&!V?R.createElement("div",{className:`${L}-extra`,id:E,"x-semi-prop":"extra"},T):null):null)}constructor(e){super(e),this.onChange=e=>{let{onChange:n}=this.props;if(this.isInGroup()){let{radioGroup:n}=this.context;n.onChange&&n.onChange(e)}"checked"in this.props||this.foundation.setChecked(e.target.checked),n&&n(e)},this.handleMouseEnter=e=>{this.props.onMouseEnter(e),this.foundation.setHover(!0)},this.handleMouseLeave=e=>{this.props.onMouseLeave(e),this.foundation.setHover(!1)},this.handleFocusVisible=e=>{this.foundation.handleFocusVisible(e)},this.handleBlur=e=>{this.foundation.handleBlur()},this.state={hover:!1,addonId:e.addonId,extraId:e.extraId,checked:e.checked||e.defaultChecked||!1},this.foundation=new p.Z(this.adapter),this.radioEntity=null}}X.contextType=H.Z,X.propTypes={autoFocus:c().bool,checked:c().bool,defaultChecked:c().bool,value:c().any,style:c().object,className:c().string,disabled:c().bool,prefixCls:c().string,displayMode:c().oneOf(["vertical",""]),onChange:c().func,onMouseEnter:c().func,onMouseLeave:c().func,mode:c().oneOf(f.j2.MODE),extra:c().node,addonStyle:c().object,addonClassName:c().string,type:c().oneOf([f.j2.TYPE_DEFAULT,f.j2.TYPE_BUTTON,f.j2.TYPE_CARD,f.j2.TYPE_PURECARD]),"aria-label":c().string,preventScroll:c().bool},X.defaultProps={autoFocus:!1,defaultChecked:!1,value:void 0,style:void 0,onMouseEnter:s(),onMouseLeave:s(),mode:"",type:"default"},X.elementType="Radio",n.Z=X},917332:function(e,n,o){"use strict";o.d(n,{Z:function(){return D}}),o(370483),o(847119);var a=o(703196),t=o(408812),r=o(271838),i=o(256195),d=o.n(i),s=o(794840),R=o(751861),l=o(861275),c=o.n(l),u=o(137942),h=o(784109),p=o(368914),f=o(889660);o(768737);var M=function(e,n){var o={};for(var a in e)Object.prototype.hasOwnProperty.call(e,a)&&0>n.indexOf(a)&&(o[a]=e[a]);if(null!=e&&"function"==typeof Object.getOwnPropertySymbols)for(var t=0,a=Object.getOwnPropertySymbols(e);t<a.length;t++)0>n.indexOf(a[t])&&Object.prototype.propertyIsEnumerable.call(e,a[t])&&(o[a[t]]=e[a[t]]);return o};class D extends r.Z{static getDerivedStateFromProps(e,n){return"value"in e&&void 0!==e.value?Object.assign(Object.assign({},n),{value:e.value}):n}get adapter(){return Object.assign(Object.assign({},super.adapter),{focus:()=>{let{disabled:e,count:n}=this.props,{value:o}=this.state;if(!e){let e=Math.ceil(o)-1;this.stars[e<0?n:e].starFocus()}},getStarDOM:e=>{let n=this.stars&&this.stars[e];return t.findDOMNode(n)},notifyHoverChange:(e,n)=>{let{onHoverChange:o}=this.props;this.setState({hoverValue:e,clearedValue:n}),o(e)},updateValue:e=>{let{onChange:n}=this.props;!("value"in this.props)&&this.setState({value:e}),n(e)},clearValue:e=>{this.setState({clearedValue:e})},notifyFocus:e=>{let{onFocus:n}=this.props;this.setState({focused:!0}),n&&n(e)},notifyBlur:e=>{let{onBlur:n}=this.props;this.setState({focused:!1}),n&&n(e)},notifyKeyDown:e=>{let{onKeyDown:n}=this.props;this.setState({focused:!1}),n&&n(e)},setEmptyStarFocusVisible:e=>{this.setState({emptyStarFocusVisible:e})}})}componentDidMount(){this.foundation.init()}componentWillUnmount(){this.foundation.destroy()}render(){let e=this.props,{style:n,prefixCls:o,disabled:t,className:r,id:i,count:s,tabIndex:R}=e,l=M(e,["style","prefixCls","disabled","className","id","count","tabIndex"]),{value:c,emptyStarFocusVisible:h}=this.state,p=this.getAriaLabelPrefix(),f=`Rating: ${c} of ${s} ${p}${1===c?"":"s"},`,D=this.getItemList(p),g=d()(o,{[`${o}-disabled`]:t,[`${o}-focus`]:h},r);return a.createElement("ul",Object.assign({"aria-label":f,"aria-labelledby":this.props["aria-labelledby"],"aria-describedby":this.props["aria-describedby"],className:g,style:n,onMouseLeave:t?u.Z:this.onMouseLeave,tabIndex:t?-1:R,onFocus:t?u.Z:this.onFocus,onBlur:t?u.Z:this.onBlur,onKeyDown:t?u.Z:this.onKeyDown,ref:this.saveRate,id:i},this.getDataAttr(l)),D)}constructor(e){super(e),this.rate=null,this.onHover=(e,n)=>{this.foundation.handleHover(e,n)},this.onMouseLeave=()=>{this.foundation.handleMouseLeave()},this.onClick=(e,n)=>{this.foundation.handleClick(e,n)},this.onFocus=e=>{this.foundation.handleFocus(e)},this.onBlur=e=>{this.foundation.handleBlur(e)},this.onKeyDown=e=>{let{value:n}=this.state;this.foundation.handleKeyDown(e,n)},this.focus=()=>{let{disabled:e,preventScroll:n}=this.props;!e&&this.rate.focus({preventScroll:n})},this.blur=()=>{let{disabled:e}=this.props;!e&&this.rate.blur()},this.saveRef=e=>n=>{this.stars[e]=n},this.saveRate=e=>{this.rate=e},this.handleStarFocusVisible=e=>{this.foundation.handleStarFocusVisible(e)},this.handleStarBlur=e=>{this.foundation.handleStarBlur(e)},this.getAriaLabelPrefix=()=>{if(this.props["aria-label"])return this.props["aria-label"];let e="star",{character:n}=this.props;return"string"==typeof n&&(e=n),e},this.getItemList=e=>{let{count:n,allowHalf:o,prefixCls:t,disabled:r,character:i,size:d,tooltips:s}=this.props,{value:R,hoverValue:l,focused:c}=this.state;return[...Array(n+1).keys()].map(f=>{let M=a.createElement(h.Z,{ref:this.saveRef(f),index:f,count:n,prefixCls:`${t}-star`,allowHalf:o,value:void 0===l?R:l,onClick:r?u.Z:this.onClick,onHover:r?u.Z:this.onHover,key:f,disabled:r,character:i,focused:c,size:f===n?0:d,ariaLabelPrefix:e,onFocus:r||n!==f?u.Z:this.handleStarFocusVisible,onBlur:r||n!==f?u.Z:this.handleStarBlur});if(s){let e=s[f]?s[f]:"",n=l-1===f;return a.createElement(p.Z,{visible:n,trigger:"custom",content:e,key:`${f}-${n}`},M)}return M})};let n=void 0===e.value?e.defaultValue:e.value;this.stars={},this.state={value:n,focused:!1,hoverValue:void 0,clearedValue:null,emptyStarFocusVisible:!1},this.foundation=new f.Z(this.adapter)}}D.contextType=s.Z,D.propTypes={"aria-describedby":c().string,"aria-errormessage":c().string,"aria-invalid":c().bool,"aria-label":c().string,"aria-labelledby":c().string,"aria-required":c().bool,disabled:c().bool,value:c().number,defaultValue:c().number,count:c().number,allowHalf:c().bool,allowClear:c().bool,style:c().object,prefixCls:c().string,onChange:c().func,onHoverChange:c().func,className:c().string,character:c().node,tabIndex:c().number,onFocus:c().func,onBlur:c().func,onKeyDown:c().func,autoFocus:c().bool,size:c().oneOfType([c().oneOf(R.j.SIZE_SET),c().number]),tooltips:c().arrayOf(c().string),id:c().string,preventScroll:c().bool},D.defaultProps={defaultValue:0,count:5,allowHalf:!1,allowClear:!0,style:{},prefixCls:R.U.PREFIX,onChange:u.Z,onHoverChange:u.Z,tabIndex:-1,size:"default"}},66380:function(e,n,o){"use strict";o(370483);var a=o(703196),t=o(256195),r=o.n(t),i=o(861275),d=o.n(i),s=o(660629),R=o(906943),l=o(271838);let c=R.U.PREFIX;class u extends l.Z{componentDidMount(){this.foundation.init()}componentDidUpdate(e){}componentWillUnmount(){this.foundation.destroy()}get adapter(){return Object.assign(Object.assign({},super.adapter),{registerEvent:()=>{this.resizeHandlerRef.current.addEventListener("mousedown",this.foundation.onMouseDown),this.resizeHandlerRef.current.addEventListener("touchstart",this.foundation.onTouchStart)},unregisterEvent:()=>{this.resizeHandlerRef.current.removeEventListener("mousedown",this.foundation.onMouseDown),this.resizeHandlerRef.current.removeEventListener("touchstart",this.foundation.onTouchStart)}})}render(){let{children:e,style:n,className:o}=this.props;return a.createElement("div",{className:r()(o,c+"-resizableHandler",c+"-resizableHandler-"+this.props.direction),style:Object.assign({},n),ref:this.resizeHandlerRef},e)}constructor(e){super(e),this.state={direction:this.props.direction},this.resizeHandlerRef=(0,a.createRef)(),this.foundation=new s.U(this.adapter)}}u.propTypes={children:d().node,direction:d().string,onResizeStart:d().func,className:d().string,disabled:d().bool,style:d().object},u.defaultProps={},n.Z=u},309552:function(e,n,o){"use strict";o.d(n,{Z:function(){return R},t:function(){return s}}),o(847119),o(870128),o(97653);var a=o(703196),t=o(408812),r=o(861275),i=o.n(r),d=o(271838),s={Width:"width",Height:"height",All:"all"};class R extends d.Z{componentDidMount(){var e;null===(e=this.observeElement)||void 0===e||e.call(this)}componentDidUpdate(e){var n;null===(n=this.observeElement)||void 0===n||n.call(this,this.props.observeParent!==e.observeParent)}componentWillUnmount(){this.observer&&(this.observer.disconnect(),this.observer=null,this.element=null)}render(){let e=a.Children.only(this.props.children),{ref:n}=e;return a.cloneElement(e,{ref:e=>this.mergeRef(n,e)})}constructor(e){var n;super(e),n=this,this.formerPropertyValue=new Map,this.getElement=()=>{try{return(0,t.findDOMNode)(this.childNode||this)}catch(e){return null}},this.handleResizeEventTriggered=e=>{var n,o,a,t;if(this.props.observerProperty===s.All)null===(o=(n=this.props).onResize)||void 0===o||o.call(n,e);else{let n=[];for(let o of e)this.formerPropertyValue.has(o.target)?o.contentRect[this.props.observerProperty]!==this.formerPropertyValue.get(o.target)&&(this.formerPropertyValue.set(o.target,o.contentRect[this.props.observerProperty]),n.push(o)):(this.formerPropertyValue.set(o.target,o.contentRect[this.props.observerProperty]),n.push(o));n.length>0&&(null===(t=(a=this.props).onResize)||void 0===t||t.call(a,n))}},this.observeElement=function(){let e=arguments.length>0&&void 0!==arguments[0]&&arguments[0],o=n.getElement();if(!n.observer&&(n.observer=new ResizeObserver(n.handleResizeEventTriggered)),!(o&&o instanceof Element)){n.observer.disconnect();return}if(o!==n.element||!!e){n.observer.disconnect(),n.element=o;n.observer.observe(o),n.props.observeParent&&o.parentNode&&o.parentNode.ownerDocument&&o.parentNode.ownerDocument.defaultView&&o.parentNode instanceof o.parentNode.ownerDocument.defaultView.HTMLElement&&(n._parentNode=o.parentNode,n.observer.observe(n._parentNode))}},this.mergeRef=(e,n)=>{this.childNode=n,"function"==typeof e?e(n):"object"==typeof e&&e&&"current"in e&&(e.current=n)},globalThis.ResizeObserver&&(this.observer=new ResizeObserver(this.handleResizeEventTriggered))}}R.propTypes={onResize:i().func,observeParent:i().bool,observerProperty:i().string,delayTick:i().number},R.defaultProps={onResize:()=>{},observeParent:!1,observerProperty:"all",delayTick:0}},55688:function(e,n,o){"use strict";o.d(n,{Dx:function(){return D},Ee:function(){return M},nv:function(){return H},qE:function(){return f},zx:function(){return g}}),o(370483),o(847119);var a=o(703196),t=o(256195),r=o.n(t),i=o(861275),d=o.n(i),s=o(518947),R=o(753708);o(225511);var l=function(e,n){var o={};for(var a in e)Object.prototype.hasOwnProperty.call(e,a)&&0>n.indexOf(a)&&(o[a]=e[a]);if(null!=e&&"function"==typeof Object.getOwnPropertySymbols)for(var t=0,a=Object.getOwnPropertySymbols(e);t<a.length;t++)0>n.indexOf(a[t])&&Object.prototype.propertyIsEnumerable.call(e,a[t])&&(o[a[t]]=e[a[t]]);return o};let c=R.j.SIZE,u=R.j.SHAPE,h=e=>n=>o=>a.createElement(n,Object.assign({type:e},o));class p extends a.PureComponent{render(){let e=this.props,{prefixCls:n,className:o,type:t,size:i,shape:d}=e,s=l(e,["prefixCls","className","type","size","shape"]),R=r()(o,`${n}-${t}`,{[`${n}-${t}-${i}`]:"AVATAR"===t.toUpperCase()},{[`${n}-${t}-${d}`]:"AVATAR"===t.toUpperCase()});return a.createElement("div",Object.assign({className:R},s))}}p.propTypes={type:d().string,prefixCls:d().string,style:d().object,className:d().string,size:d().oneOf(c),shape:d().oneOf(u)},p.defaultProps={prefixCls:s.U.PREFIX,size:"medium",shape:"circle"};let f=h("avatar")(p),M=h("image")(p),D=h("title")(p),g=h("button")(p);class H extends a.PureComponent{render(){let{prefixCls:e,className:n,style:o,rows:t}=this.props,i=r()(n,`${e}-paragraph`);return a.createElement("ul",{className:i,style:o},[...Array(t)].map((e,n)=>a.createElement("li",{key:n})))}}H.propTypes={rows:d().number,prefixCls:d().string,style:d().object,className:d().string},H.defaultProps={prefixCls:s.U.PREFIX,rows:4}},143783:function(e,n,o){"use strict";var a=o(861275),t=o.n(a),r=o(26910);n.Z={align:t().oneOf(r.j2.ALIGNS),className:t().string,colSpan:t().number,dataIndex:t().string,defaultSortOrder:t().oneOf(r.j2.SORT_DIRECTIONS),filterChildrenRecord:t().bool,filterDropdownProps:t().object,filterDropdown:t().node,filterDropdownVisible:t().bool,filterIcon:t().func,filterMultiple:t().bool,filteredValue:t().arrayOf(t().any),filters:t().array,fixed:t().oneOf(r.j2.FIXED_SET),onCell:t().func,onFilter:t().func,onFilterDropdownVisibleChange:t().func,onHeaderCell:t().func,onSorterChange:t().func,render:t().func,renderFilterDropdownItem:t().func,sortChildrenRecord:t().bool,sortDirections:t().arrayOf(t().string),sortOrder:t().oneOfType([t().bool,t().string]),sorter:t().oneOfType([t().bool,t().func]),title:t().oneOfType([t().func,t().node]),useFullRender:t().bool,width:t().oneOfType([t().number,t().string]),showSortTip:t().bool}},625523:function(e,n,o){"use strict";var a=o(639444),t=o.n(a);let r=o(703196).createContext({headWidths:[],setHeadWidths:t(),handleRowExpanded:t()});n.Z=r},719694:function(e,n,o){"use strict";o.d(n,{Z:function(){return s}}),o(370483);var a=o(703196),t=o(861275),r=o.n(t),i=o(266533),d=o(951328);class s extends a.PureComponent{render(){return a.createElement(d.Z,Object.assign({component:"span"},this.props))}}s.propTypes={copyable:r().oneOfType([r().object,r().bool]),delete:r().bool,disabled:r().bool,icon:r().oneOfType([r().node,r().string]),ellipsis:r().oneOfType([r().object,r().bool]),mark:r().bool,underline:r().bool,link:r().oneOfType([r().object,r().bool]),strong:r().bool,type:r().oneOf(i.j.TYPE),size:r().oneOf(i.j.SIZE),style:r().object,className:r().string,code:r().bool,component:r().string,weight:r().number},s.defaultProps={copyable:!1,delete:!1,disabled:!1,icon:"",ellipsis:!1,mark:!1,underline:!1,strong:!1,link:!1,type:"primary",style:{},size:"normal",className:""}},909999:function(e,n,o){"use strict";o.d(n,{G:function(){return R}});var a=o(203687),t=o(258343),r=o(254859),i=o(820429),d=o(445068),s=o(344985);class R extends r.v{init(e){if(this._media=e,e.addEventListener("timeupdate",this.handleTimeupdate),e.autoplay){let n=()=>{e.removeEventListener("canplay",n),e.play().catch(()=>{null==e||e.dispatchEvent(new CustomEvent(s.c.AUTOPLAY_WAS_PREVENTED,{}))})};e.addEventListener("canplay",n)}this.initPlugins()}initPlugins(){let{plugins:e}=this.config;e&&(this.plugins=e.map(e=>new e(this))),this.plugins.forEach(e=>{e.afterPlayerInit()})}playBy(){var e;let n=arguments.length>0&&void 0!==arguments[0]?arguments[0]:{},{url:o}=n;this.updateProtoConfig(n),this.emit(i.Zo.URLCHANGE,{url:o}),this._onSwitchURL(n.url),null===(e=this.media)||void 0===e||e.dispatchEvent(new CustomEvent("loadstart",{}))}updateProtoConfig(){let e=arguments.length>0&&void 0!==arguments[0]?arguments[0]:{},n=(0,d.i)((0,t._)({},this.config,e));return this.config=n,n}reset(){this.destroy()}get src(){var e;return null===(e=this._media)||void 0===e?void 0:e.src}get buffered(){var e;return null===(e=this.media)||void 0===e?void 0:e.buffered}get currentTime(){var e;return null===(e=this.media)||void 0===e?void 0:e.currentTime}get duration(){var e;return null===(e=this.media)||void 0===e?void 0:e.duration}get media(){return this._media}get speed(){var e;return null===(e=this.media)||void 0===e?void 0:e.playbackRate}set speed(e){this.speed!==e&&(this.media.playbackRate=e)}get bufferLength(){let{currentTime:e=0,buffered:n}=this._media||{};if(!n)return 0;for(let o=0;o<n.length;o++){let a=n.end(o);if(n.start(o)<=e&&a>=e)return(a-e)*1e3}return 0}play(){var e;return null===(e=this._media)||void 0===e?void 0:e.play()}constructor(e,n){super(),(0,a._)(this,"_media",null),(0,a._)(this,"config",{}),(0,a._)(this,"plugins",[]),(0,a._)(this,"destroy",()=>{var e;this.removeAllListeners(),null===(e=this._media)||void 0===e||e.removeEventListener("timeupdate",this.handleTimeupdate),this.plugins.forEach(e=>{e.destroy()})}),(0,a._)(this,"_onSwitchURL",e=>{var n;this._media&&(this._media.src=e,(null===(n=this.config)||void 0===n?void 0:n.keepStatusAfterSwitch)&&this._keepPauseStatus())}),(0,a._)(this,"_keepPauseStatus",()=>{var e,n;if(!(null===(e=this._media)||void 0===e?void 0:e.paused))return;let o=()=>{var e,n;null===(e=this.media)||void 0===e||e.removeEventListener("canplay",o),null===(n=this._media)||void 0===n||n.pause()};null===(n=this.media)||void 0===n||n.addEventListener("canplay",o)}),(0,a._)(this,"handleTimeupdate",()=>{let e=this.bufferLength;1.1===this.speed?e<=1800&&(this.speed=1):1===this.speed&&e>=2500&&(this.speed=1.1)}),this.config=this.updateProtoConfig(n),this.init(e)}}},256594:function(e,n,o){"use strict";o.d(n,{y:function(){return p}});var a=o(203687),t=o(275909);o(924006),o(870128),o(847119),o(46163),o(207418),o(118703),o(388642),o(19526),o(141857);var r=o(897118),i=o(250515),d=o(694380),s=o(651676),R=o(186411),l=o(767616),c=o(521507),u=o(107278);let h=new R.ZP("BufferService");class p{get baseDts(){var e,n,o;return null===(o=this._transmuxer)||void 0===o?void 0:null===(n=o._demuxer)||void 0===n?void 0:null===(e=n._fixer)||void 0===e?void 0:e._baseDts}get nbSb(){var e;return(null===(e=this._mse)||void 0===e?void 0:e._sourceBuffer)?Object.keys(this._mse._sourceBuffer).length:0}get msIsOpened(){var e;return null===(e=this._mse)||void 0===e?void 0:e.isOpened}get msHasOpTasks(){var e;return null===(e=this._mse)||void 0===e?void 0:e.hasOpTasks}get msStreaming(){var e;return null===(e=this._mse)||void 0===e?void 0:e.streaming}async updateDuration(e){h.debug("update duration",e),this._mse?(!this._mse.isOpened&&await this._mse.open(),await this._mse.updateDuration(e)):this._softVideo&&(this._softVideo.duration=e)}createSource(e,n,o,a){if(this._sourceCreated)return;let t=e||n;if(t){if(r.ht.probe(t))!this._transmuxer&&(this._transmuxer=new c.g(this.hls,!1,!this._softVideo,this.hls.config.fixerConfig));else throw new s.Fc("other",null,null,null,"unsupported stream");this._softVideo&&(this._sourceCreated=!0)}}async appendBuffer(e,n,o,a,r,d,s){if(!(null==o?void 0:o.length)&&!(null==a?void 0:a.length))return;let R=()=>{};if(this._directAppend){let e=[];return o&&e.push(this._mse.append(i.d1.VIDEO,o)),a&&e.push(this._mse.append(i.d1.AUDIO,a)),Promise.all(e).then(R)}let l=this._needInitSegment||r,[c,h]=this._transmuxer.transmux(o,a,l,d,s,this._needInitSegment||r);if(a&&n&&(null==n||n.setTrackExist(!1,!0)),a&&e&&(null==e||e.setTrackExist(!0,!1)),!n&&(null==e||e.setTrackExist(!!c,!!h)),c&&!h&&this.hls.emit(u.j.NO_AUDIO_TRACK),this._softVideo)this._softVideo.appendBuffer(c,h),this._needInitSegment=!1,R();else if(this._mse){let e=!this._sourceCreated;e&&this._createMseSource(null==c?void 0:c.codec,null==h?void 0:h.codec,null==h?void 0:h.container),this._needInitSegment=!1;let n=this._mse,o=[];if(l&&!e&&this._handleCodecChange(c,h).forEach(e=>o.push(e)),c){let{data:e}=c,a=(0,t._)(c,["data"]);o.push(n.append(i.d1.VIDEO,e,a))}if(h){let{data:e}=h,a=(0,t._)(h,["data"]);o.push(n.append(i.d1.AUDIO,e,a))}let a=Promise.all(o);return a.then(R),a}}async removeBuffer(){let e=arguments.length>0&&void 0!==arguments[0]?arguments[0]:0,n=arguments.length>1&&void 0!==arguments[1]?arguments[1]:1/0,o=this.hls.media;if(this._mse&&o&&!(e<0)&&!(n<e)&&!(e>=this._mse.duration))return this._mse.clearBuffer(e,n)}async evictBuffer(e){let n=this.hls.media;if(!this._mse||!n||!e||e<0)return;let o=n.currentTime-e;if(!(o<=0)){if(!(d.l.start(d.l.get(n))+1>=o))return this.removeBuffer(0,o)}}async clearAllBuffer(){if(this._mse)return this._mse.clearAllBuffer()}decryptBuffer(e,n){return this._decryptor.decrypt(e,n)}async reset(){let e=arguments.length>0&&void 0!==arguments[0]&&arguments[0];this._mse&&!e&&(this._transmuxer=null,this._sourceCreated=!1,await this._mse.unbindMedia(),await this._mse.bindMedia(this.hls.media)),this._needInitSegment=!0,this._directAppend=!1}async endOfStream(){this._mse&&this._sourceCreated&&await this._mse.endOfStream(),this._softVideo&&this._softVideo.endOfStream()}async setLiveSeekableRange(e,n){this._mse&&this._mse.setLiveSeekableRange(e,n)}async detachMedia(){this._mse&&await this._mse.unbindMedia()}async destroy(){var e;null===(e=this._decryptor)||void 0===e||e.destroy(),await this.detachMedia(),this._decryptor=null,this._mse=null,this._softVideo=null}_createMseSource(e,n,o){h.debug(`create mse source, videoCodec=${e}, audioCodec=${n}`);let a=this._mse;a&&(e&&(a.createSource(i.d1.VIDEO,`video/mp4;codecs=${e}`),this._sourceCreated=!0),n?(a.createSource(i.d1.AUDIO,`audio/mp4;codecs=${n}`),this._sourceCreated=!0):o&&(a.createSource(i.d1.AUDIO,`${o};codecs=""`),this._sourceCreated=!0))}_handleCodecChange(e,n){let o=[],a=this._mse;return[{type:i.d1.VIDEO,codecs:null==e?void 0:e.codec},{type:i.d1.AUDIO,codecs:null==n?void 0:n.codec}].filter(e=>!!e.codecs).forEach(e=>{let{type:n,codecs:t}=e,r=a.getSourceBuffer(n);r&&!RegExp(t.split(",")[0],"ig").test(r.mimeType)&&o.push(a.changeType(n,`${n}/mp4;codecs=${t}`))}),o}seamlessSwitch(){this._needInitSegment=!0}isFull(){var e;let n=arguments.length>0&&void 0!==arguments[0]?arguments[0]:i.d1.VIDEO;return null===(e=this._mse)||void 0===e?void 0:e.isFull(n)}constructor(e){(0,a._)(this,"_decryptor",new l.$),(0,a._)(this,"_transmuxer",null),(0,a._)(this,"_mse",null),(0,a._)(this,"_softVideo",null),(0,a._)(this,"_sourceCreated",!1),(0,a._)(this,"_needInitSegment",!0),(0,a._)(this,"_directAppend",!1),this.hls=e,e.config.softDecode?this._softVideo=e.media:(this._mse=new i.d1(null,{preferMMS:e.config.preferMMS}),e.config.url&&this._mse.bindMedia(e.media).then(e=>{})),e.config.decryptor&&(this._decryptor.externalDecryptor=e.config.decryptor)}}},912247:function(e,n,o){"use strict";o.d(n,{i:function(){return s}});var a=o(275909);o(924006);var t=o(778926),r=o(613561),i=o(271698),d=o(186411);class s{exec(){let e=this._config,{retry:n,retryDelay:o,onRetryError:t,transformError:r}=e,i=(0,a._)(e,["retry","retryDelay","onRetryError","transformError"]),d=async()=>{try{let e=await this._loader.load(i);this.promise.resolve(e)}catch(s){if(this._loader.running=!1,this._logger.debug("[task request catch err]",s),this._canceled)return;s.loaderType=this._loaderType,s.retryCount=this._retryCount;let e=s;r&&(e=r(e)||e),t&&this._retryCount>0&&t(e,this._retryCount,{index:i.index,vid:i.vid,range:i.range,priOptions:i.priOptions}),this._retryCount++;let a=!0;if(this._retryCheckFunc&&(a=this._retryCheckFunc(s)),a&&this._retryCount<=n){clearTimeout(this._retryTimer),this._logger.debug("[task request setTimeout],retry",this._retryCount,",retry range,",i.range),this._retryTimer=setTimeout(d,o);return}this.promise.reject(e)}};return d(),this.promise}async cancel(){return clearTimeout(this._retryTimer),this._canceled=!0,this._loader.running=!1,this._loader.cancel()}get running(){return this._loader&&this._loader.running}get loader(){return this._loader}constructor(e,n){this.promise=(0,i.Qo)(),this.alive=!!n.onProgress,n.logger||(n.logger=new d.ZP("Loader")),this._loaderType=e,this._loader=e===r.t.FETCH&&"undefined"!=typeof fetch?new t.j:new XhrLoader,this._config=n,this._retryCount=0,this._retryTimer=null,this._canceled=!1,this._retryCheckFunc=n.retryCheckFunc,this._logger=n.logger}}},616210:function(e,n,o){"use strict";function a(){let e,n;let o=new Promise((o,a)=>{e=o,n=a});return o.resolve=function(){for(var n=arguments.length,o=Array(n),a=0;a<n;a++)o[a]=arguments[a];return e(...o)},o.reject=function(){for(var e=arguments.length,o=Array(e),a=0;a<e;a++)o[a]=arguments[a];return n(...o)},o}o.d(n,{Q:function(){return a}}),o(924006),o(847119)},432349:function(e,n,o){"use strict";o.d(n,{W:function(){return r}});var a=o(203687);o(877782),o(870128),o(694091),o(946926),o(99547),o(444166),o(235813),o(584105),o(46596);var t=o(774374);class r{static getRateIndexByRate(e){return r.FREQ.indexOf(e)}static parseADTS(e,n){let o,a;let t=e.length,i=0;for(;i+2<t&&(255!==e[i]||(246&e[i+1])!=240);){;i++}if(i>=t)return;let d=i,s=[],R=(60&e[i+2])>>>2,l=r.FREQ[R];if(!l)throw Error(`Invalid sampling index: ${R}`);let c=((192&e[i+2])>>>6)+1,u=(1&e[i+2])<<2|(192&e[i+3])>>>6,{config:h,codec:p}=r._getConfig(R,u,c),f=0,M=r.getFrameDuration(l);for(;i+7<t;){if(255!==e[i]||(246&e[i+1])!=240){i++;continue}if(!(a=(3&e[i+3])<<11|e[i+4]<<3|(224&e[i+5])>>5)||t-i<a)break;o=(1&~e[i+1])*2,s.push({pts:n+f*M,data:e.subarray(i+7+o,i+a)}),f++,i+=a}return{skip:d,remaining:i>=t?void 0:e.subarray(i),frames:s,samplingFrequencyIndex:R,sampleRate:l,objectType:c,channelCount:u,codec:p,config:h,originCodec:`mp4a.40.${c}`}}static parseAudioSpecificConfig(e){if(!e.length)return;let n=e[0]>>>3,o=(7&e[0])<<1|e[1]>>>7,a=(120&e[1])>>>3,t=r.FREQ[o];if(!t)return;let{config:i,codec:d}=r._getConfig(o,a,n);return{samplingFrequencyIndex:o,sampleRate:t,objectType:n,channelCount:a,config:i,codec:d,originCodec:`mp4a.40.${n}`}}static getFrameDuration(e){let n=arguments.length>1&&void 0!==arguments[1]?arguments[1]:9e4;return 1024*n/e}static _getConfig(e,n,o){let a,r;let i=[];return t.vU?e>=6?(a=5,r=e-3):(a=2,r=e):t.Dt?(a=2,r=e):(a=2===o||5===o?o:5,r=e,e>=6?r=e-3:1===n&&(a=2,r=e)),i[0]=a<<3,i[0]|=(14&e)>>1,i[1]=(1&e)<<7,i[1]|=n<<3,5===a&&(i[1]|=(14&r)>>1,i[2]=(1&r)<<7,i[2]|=8,i[3]=0),{config:i,codec:`mp4a.40.${a}`}}static getSilentFrame(e,n){if("mp4a.40.2"===e){if(1===n)return new Uint8Array([0,200,0,128,35,128]);if(2===n)return new Uint8Array([33,0,73,144,2,25,0,35,128]);if(3===n)return new Uint8Array([0,200,0,128,32,132,1,38,64,8,100,0,142]);if(4===n)return new Uint8Array([0,200,0,128,32,132,1,38,64,8,100,0,128,44,128,8,2,56]);if(5===n)return new Uint8Array([0,200,0,128,32,132,1,38,64,8,100,0,130,48,4,153,0,33,144,2,56]);if(6===n)return new Uint8Array([0,200,0,128,32,132,1,38,64,8,100,0,130,48,4,153,0,33,144,2,0,178,0,32,8,224])}else{if(1===n)return new Uint8Array([1,64,34,128,163,78,230,128,186,8,0,0,0,28,6,241,193,10,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,94]);if(2===n||3===n)return new Uint8Array([1,64,34,128,163,94,230,128,186,8,0,0,0,0,149,0,6,241,161,10,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,94])}}}(0,a._)(r,"FREQ",[96e3,88200,64e3,48e3,44100,32e3,24e3,22050,16e3,12e3,11025,8e3,7350])},272737:function(e,n,o){"use strict";o.d(n,{U:function(){return t}});var a=o(776045);let t={PREFIX:`${a.T}-backtop`}},500175:function(e,n,o){"use strict";o.d(n,{Z:function(){return f}}),o(370483),o(847119),o(870128),o(46163),o(207418),o(295655),o(428647),o(19526);var a=o(405069),t=o.n(a),r=o(36191),i=o(843649),d=o(794904),s=o(889287),R=o(308518);let{PIC_PREFIX:l,PIC_SUFFIX_ARRAY:c,ROLE:u,SCROLL_ANIMATION_TIME:h,SHOW_SCROLL_GAP:p}=i.j;class f extends r.Z{constructor(e){super(Object.assign({},e)),this.init=()=>{this.scrollToBottomImmediately(),this._adapter.registerWheelEvent()},this.destroy=()=>{this.animation&&this.animation.destroy(),this._adapter.unRegisterWheelEvent()},this.stopGenerate=e=>{this._adapter.notifyStopGenerate(e)},this.scrollToBottomImmediately=()=>{let e=this._adapter.getContainerRef();e&&(e.scrollTop=e.scrollHeight)},this.scrollToBottomWithAnimation=()=>{let e=this._adapter.getContainerRef();if(!e)return;let n=e.scrollTop,o=e.scrollHeight;this.animation=new d.fw({from:{scrollTop:n},to:{scrollTop:o}},{duration:h,easing:"easeInOutCubic"}),this.animation.on("frame",n=>{let{scrollTop:o}=n;e.scrollTop=o}),this.animation.start()},this.containerScroll=e=>{this._persistEvent(e);requestAnimationFrame(()=>{this.getScroll(e.target)})},this.getScroll=t()(e=>{let n=e.scrollHeight,o=e.clientHeight,a=e.scrollTop,{backBottomVisible:t}=this.getStates();return n-a-o<=p?t&&this._adapter.setBackBottomVisible(!1):!t&&this._adapter.setBackBottomVisible(!0),scroll},100),this.clearContext=e=>{let{chats:n}=this.getStates();if(n[n.length-1].role===u.DIVIDER)return;let o=[...n,{role:u.DIVIDER,id:(0,s.Cd)(),createAt:Date.now()}];this._adapter.notifyChatsChange(o),this._adapter.notifyClearContext()},this.onMessageSend=(e,n)=>{let o;if(n&&0===n.length?o=e:(o=[],e&&o.push({type:"text",text:e}),(null!=n?n:[]).map(e=>{var n;let{fileInstance:a,name:t="",url:r,size:i}=e,d=t.split(".").pop();(null===(n=null==a?void 0:a.type)||void 0===n?void 0:n.startsWith(l))||c.includes(d)?o.push({type:"image_url",image_url:{url:r}}):o.push({type:"file_url",file_url:{url:r,name:t,size:i,type:null==a?void 0:a.type}})})),o){let e={role:u.USER,id:(0,s.Cd)(),createAt:Date.now(),content:o};this._adapter.notifyChatsChange([...this.getStates().chats,e])}this._adapter.setWheelScroll(!1),this._adapter.registerWheelEvent(),this._adapter.notifyMessageSend(e,n)},this.onHintClick=e=>{let{chats:n}=this.getStates(),o=[...n,{role:u.USER,id:(0,s.Cd)(),createAt:Date.now(),content:e}];this._adapter.notifyChatsChange(o),this._adapter.notifyHintClick(e)},this.onInputChange=e=>{this._adapter.notifyInputChange(e)},this.deleteMessage=e=>{let{onMessageDelete:n,onChatsChange:o}=this.getProps(),{chats:a}=this.getStates();null==n||n(e);let t=a.filter(n=>n.id!==e.id);null==o||o(t)},this.likeMessage=e=>{let{chats:n}=this.getStates();this._adapter.notifyLikeMessage(e);let o=n.findIndex(n=>n.id===e.id),a=Object.assign(Object.assign({},n[o]),{like:!n[o].like,dislike:!1}),t=[...n];t.splice(o,1,a),this._adapter.notifyChatsChange(t)},this.dislikeMessage=e=>{let{chats:n}=this.getStates();this._adapter.notifyDislikeMessage(e);let o=n.findIndex(n=>n.id===e.id),a=Object.assign(Object.assign({},n[o]),{like:!1,dislike:!n[o].dislike}),t=[...n];t.splice(o,1,a),this._adapter.notifyChatsChange(t)},this.resetMessage=e=>{let{chats:n}=this.getStates(),o=Object.assign(Object.assign({},n[n.length-1]),{status:"loading",content:"",id:(0,s.Cd)(),createAt:Date.now()}),a=n.slice(0,-1).concat(o);this._adapter.notifyChatsChange(a);let{onMessageReset:t}=this.getProps();null==t||t(e)},this.handleDragOver=e=>{if(!this._adapter.getDragStatus())this._adapter.setUploadAreaVisible(!0)},this.handleDragStart=e=>{this._adapter.setDragStatus(!0)},this.handleDragEnd=e=>{this._adapter.setDragStatus(!1)},this.handleContainerDragOver=e=>{(0,R.Jt)(e)},this.handleContainerDrop=e=>{var n;this._adapter.setUploadAreaVisible(!1),this._adapter.manualUpload(null===(n=null==e?void 0:e.dataTransfer)||void 0===n?void 0:n.files),(0,R.Jt)(e)},this.handleContainerDragLeave=e=>{(0,R.Jt)(e);let n=this._adapter.getDropAreaElement(),o=e.relatedTarget;if(!n.contains(o))setTimeout(()=>{this._adapter.setUploadAreaVisible(!1)})},this.getUploadProps=e=>{if("[object Object]"===Object.prototype.toString.call(e)){let{dragUpload:n=!0,clickUpload:o=!0,pasteUpload:a=!0}=e;return{dragUpload:n,clickUpload:o,pasteUpload:a}}if("boolean"==typeof e)return{dragUpload:e,clickUpload:e,pasteUpload:e};return{dragUpload:!0,clickUpload:!0,pasteUpload:!0}}}}},885925:function(e,n,o){"use strict";o.d(n,{OG:function(){return r},gX:function(){return t},j2:function(){return i}});var a=o(776045);let t={PREFIX:`${a.T}-checkbox`,INNER:`${a.T}-checkbox-inner`,TEXT:`${a.T}-checkbox-text`,INPUT:`${a.T}-checkbox-input`,CHECKED:`${a.T}-checkbox-checked`,DISABLED:`${a.T}-checkbox-disabled`,BUTTON:`${a.T}-checkbox-button`,WRAPPER:""},r={PREFIX:`${a.T}-checkboxGroup`,INNER:`${a.T}-checkboxGroup-inner`,TEXT:`${a.T}-checkboxGroup-text`,INPUT:`${a.T}-checkboxGroup-input`,CHECKED:`${a.T}-checkboxGroup-checked`,DISABLED:`${a.T}-checkboxGroup-disabled`},i={DIRECTION_SET:["horizontal","vertical"],TYPE_DEFAULT:"default",TYPE_CARD:"card",TYPE_PURECARD:"pureCard",DEFAULT_DIRECTION:"vertical"}},607602:function(e,n,o){"use strict";o.d(n,{Z:function(){return r}}),o(847119),o(870128);var a=o(36191),t=o(308518);class r extends a.Z{handleEscape(e){"custom"===this._adapter.getContext("trigger")&&(e&&(0,t.zT)(document.querySelectorAll("[data-popupid]"),e.id)).focus()}setFocusByFirstCharacter(e,n){let o=(0,t.Ir)(this.menuItemNodes,e,this.firstChars,n);o>=0&&(0,t.OA)(this.menuItemNodes,this.menuItemNodes[o])}onMenuKeydown(e){let n=(0,t.Yt)(e.target,"tooltip");!this.menuItemNodes&&(this.menuItemNodes=[...e.target.parentNode.getElementsByTagName("li")].filter(e=>"true"!==e.ariaDisabled)),0===this.firstChars.length&&this.menuItemNodes.forEach(e=>{var n;this.firstChars.push(null===(n=e.textContent.trim()[0])||void 0===n?void 0:n.toLowerCase())});let o=this.menuItemNodes.find(e=>0===e.tabIndex);switch(e.key){case" ":case"Enter":e.target.click();break;case"Escape":this.handleEscape(n);break;case"ArrowUp":(0,t.kx)(this.menuItemNodes,o),(0,t.Jt)(e);break;case"ArrowDown":(0,t.XS)(this.menuItemNodes,o),(0,t.Jt)(e);break;default:(0,t.kz)(e.key)&&this.setFocusByFirstCharacter(o,e.key)}}constructor(){super(...arguments),this.menuItemNodes=null,this.firstChars=[]}}},956965:function(e,n,o){"use strict";o.d(n,{x:function(){return R}});var a=o(988402),t=o(945054),r=o(399269),i=o(703196);let d="picture-in-picture",s=(0,i.forwardRef)((e,n)=>{let{playerRef:o}=(0,i.useContext)(a.E),t=(0,r.DM)(()=>{if(!document.pictureInPictureEnabled)return!1;let e=o.current.video;if("boolean"==typeof e.disablePictureInPicture&&!e.disablePictureInPicture||"function"==typeof e.webkitSetPresentationMode)return!0}),s=(0,r.DM)(()=>{let e=o.current.video;return document.pictureInPictureElement===e||e.webkitPresentationMode===d}),R=(0,r.DM)(()=>{if(!t())return!1;let e=o.current.video;return"function"==typeof e.webkitSetPresentationMode?e.webkitSetPresentationMode("inline"):document.exitPictureInPicture(),o.current.emit("pip_change",!1),!0}),l=(0,r.DM)(()=>{if(!t())return!1;let e=o.current.video;return"function"==typeof e.webkitSetPresentationMode?e.webkitSetPresentationMode(d):e.requestPictureInPicture(),o.current.emit("pip_change",!0),!0});return(0,i.useImperativeHandle)(n,()=>({exitPIP:R,requestPIP:l,switchPIP:()=>!!t()&&(s()?R():l())}),[]),null}),R=(0,t.n)(s,!0)},57719:function(e,n,o){"use strict";o.d(n,{$:function(){return r}});var a=o(851221),t=o(446062);let r=[a.F,t.B]},178240:function(e,n,o){"use strict";o(924006),Promise.all([o.e("74792"),o.e("1003"),o.e("13868"),o.e("88032"),o.e("86453"),o.e("35901"),o.e("24227"),o.e("78048"),o.e("31233"),o.e("18100")]).then(o.bind(o,839982))},185488:function(e,n,o){"use strict";Object.defineProperty(n,"__esModule",{value:!0}),n.default=function(e,n){if(arguments.length<1)throw TypeError("1 argument required, but only "+arguments.length+" present");if(null===e)return new Date(NaN);var o=n||{},i=null==o.additionalDigits?2:(0,a.default)(o.additionalDigits);if(2!==i&&1!==i&&0!==i)throw RangeError("additionalDigits must be 0, 1 or 2");if(e instanceof Date||"object"==typeof e&&"[object Date]"===Object.prototype.toString.call(e))return new Date(e.getTime());if("number"==typeof e||"[object Number]"===Object.prototype.toString.call(e))return new Date(e);if(!("string"==typeof e||"[object String]"===Object.prototype.toString.call(e)))return new Date(NaN);var d=function(e){var n,o={},a=s.dateTimePattern.exec(e);if(a?(o.date=a[1],n=a[3]):(a=s.datePattern.exec(e))?(o.date=a[1],n=a[2]):(o.date=null,n=e),n){var t=s.timeZone.exec(n);t?(o.time=n.replace(t[1],""),o.timeZone=t[1].trim()):o.time=n}return o}(e),l=function(e,n){var o,a=s.YYY[n],t=s.YYYYY[n];if(o=s.YYYY.exec(e)||t.exec(e)){var r=o[1];return{year:parseInt(r,10),restDateString:e.slice(r.length)}}if(o=s.YY.exec(e)||a.exec(e)){var i=o[1];return{year:100*parseInt(i,10),restDateString:e.slice(i.length)}}return{year:null}}(d.date,i),c=l.year,M=function(e,n){if(null===n)return null;if(0===e.length)return(a=new Date(0)).setUTCFullYear(n),a;if(o=s.MM.exec(e))return(a=new Date(0),h(n,t=parseInt(o[1],10)-1))?(a.setUTCFullYear(n,t),a):new Date(NaN);if(o=s.DDD.exec(e)){a=new Date(0);var o,a,t,r,i=parseInt(o[1],10);return!function(e,n){if(n<1)return!1;var o=u(e);return(!o||!(n>366))&&(!!o||!(n>365))&&!0}(n,i)?new Date(NaN):(a.setUTCFullYear(n,0,i),a)}if(o=s.MMDD.exec(e)){a=new Date(0),t=parseInt(o[1],10)-1;var d=parseInt(o[2],10);return h(n,t,d)?(a.setUTCFullYear(n,t,d),a):new Date(NaN)}if(o=s.Www.exec(e))return p(n,r=parseInt(o[1],10)-1)?R(n,r):new Date(NaN);if(o=s.WwwD.exec(e)){r=parseInt(o[1],10)-1;var l=parseInt(o[2],10)-1;return p(n,r,l)?R(n,r,l):new Date(NaN)}return null}(l.restDateString,c);if(isNaN(M))return new Date(NaN);if(!M)return new Date(NaN);var D,g=M.getTime(),H=0;if(d.time&&isNaN(H=function(e){if(n=s.HH.exec(e))return f(o=parseFloat(n[1].replace(",",".")))?o%24*36e5:NaN;if(n=s.HHMM.exec(e))return(o=parseInt(n[1],10),f(o,a=parseFloat(n[2].replace(",","."))))?o%24*36e5+6e4*a:NaN;if(n=s.HHMMSS.exec(e)){o=parseInt(n[1],10),a=parseInt(n[2],10);var n,o,a,t=parseFloat(n[3].replace(",","."));return f(o,a,t)?o%24*36e5+6e4*a+1e3*t:NaN}return null}(d.time)))return new Date(NaN);if(d.timeZone||o.timeZone){if(isNaN(D=(0,r.default)(d.timeZone||o.timeZone,new Date(g+H))))return new Date(NaN)}else D=(0,t.default)(new Date(g+H)),D=(0,t.default)(new Date(g+H+D));return new Date(g+H+D)};var a=d(o(345740)),t=d(o(738310)),r=d(o(28945)),i=d(o(189574));function d(e){return e&&e.__esModule?e:{default:e}}var s={dateTimePattern:/^([0-9W+-]+)(T| )(.*)/,datePattern:/^([0-9W+-]+)(.*)/,plainTime:/:/,YY:/^(\d{2})$/,YYY:[/^([+-]\d{2})$/,/^([+-]\d{3})$/,/^([+-]\d{4})$/],YYYY:/^(\d{4})/,YYYYY:[/^([+-]\d{4})/,/^([+-]\d{5})/,/^([+-]\d{6})/],MM:/^-(\d{2})$/,DDD:/^-?(\d{3})$/,MMDD:/^-?(\d{2})-?(\d{2})$/,Www:/^-?W(\d{2})$/,WwwD:/^-?W(\d{2})-?(\d{1})$/,HH:/^(\d{2}([.,]\d*)?)$/,HHMM:/^(\d{2}):?(\d{2}([.,]\d*)?)$/,HHMMSS:/^(\d{2}):?(\d{2}):?(\d{2}([.,]\d*)?)$/,timeZone:i.default};function R(e,n,o){n=n||0,o=o||0;var a=new Date(0);a.setUTCFullYear(e,0,4);var t=7*n+o+1-(a.getUTCDay()||7);return a.setUTCDate(a.getUTCDate()+t),a}var l=[31,28,31,30,31,30,31,31,30,31,30,31],c=[31,29,31,30,31,30,31,31,30,31,30,31];function u(e){return e%400==0||e%4==0&&e%100!=0}function h(e,n,o){if(n<0||n>11)return!1;if(null!=o){if(o<1)return!1;var a=u(e);if(a&&o>c[n]||!a&&o>l[n])return!1}return!0}function p(e,n,o){return!(n<0)&&!(n>52)&&(null==o||!(o<0)&&!(o>6))&&!0}function f(e,n,o){return(null==e||!(e<0)&&!(e>=25))&&(null==n||!(n<0)&&!(n>=60))&&(null==o||!(o<0)&&!(o>=60))&&!0}e.exports=n.default},503415:function(e,n,o){"use strict";function a(e){return e&&"undefined"!=typeof Symbol&&e.constructor===Symbol?"symbol":typeof e}o.d(n,{_:function(){return a}})},263099:function(e,n,o){"use strict";function a(e){return"object"==typeof e&&null!=e&&1===e.nodeType}function t(e,n){return(!n||"hidden"!==e)&&"visible"!==e&&"clip"!==e}function r(e,n){if(e.clientHeight<e.scrollHeight||e.clientWidth<e.scrollWidth){var o,a,r=getComputedStyle(e,null);return t(r.overflowY,n)||t(r.overflowX,n)||!!(a=function(e){if(!e.ownerDocument||!e.ownerDocument.defaultView)return null;try{return e.ownerDocument.defaultView.frameElement}catch(e){return null}}(o=e))&&(a.clientHeight<o.scrollHeight||a.clientWidth<o.scrollWidth)}return!1}function i(e,n,o,a,t,r,i,d){return r<e&&i>n||r>e&&i<n?0:r<=e&&d<=o||i>=n&&d>=o?r-e-a:i>n&&d<o||r<e&&d>o?i-n+t:0}o.d(n,{Z:function(){return d}});var d=function(e,n){var o=window,t=n.scrollMode,d=n.block,s=n.inline,R=n.boundary,l=n.skipOverflowHiddenElements,c="function"==typeof R?R:function(e){return e!==R};if(!a(e))throw TypeError("Invalid target");for(var u,h,p=document.scrollingElement||document.documentElement,f=[],M=e;a(M)&&c(M);){if((M=null==(h=(u=M).parentElement)?u.getRootNode().host||null:h)===p){f.push(M);break}null!=M&&M===document.body&&r(M)&&!r(document.documentElement)||null!=M&&r(M,l)&&f.push(M)}for(var D=o.visualViewport?o.visualViewport.width:innerWidth,g=o.visualViewport?o.visualViewport.height:innerHeight,H=window.scrollX||pageXOffset,m=window.scrollY||pageYOffset,X=e.getBoundingClientRect(),v=X.height,T=X.width,S=X.top,b=X.right,y=X.bottom,G=X.left,P="start"===d||"nearest"===d?S:"end"===d?y:S+v/2,A="center"===s?G+T/2:"end"===s?b:G,x=[],E=0;E<f.length;E++){var F=f[E],w=F.getBoundingClientRect(),C=w.height,V=w.width,L=w.top,_=w.right,O=w.bottom,k=w.left;if("if-needed"===t&&S>=0&&G>=0&&y<=g&&b<=D&&S>=L&&y<=O&&G>=k&&b<=_)break;var I=getComputedStyle(F),W=parseInt(I.borderLeftWidth,10),N=parseInt(I.borderTopWidth,10),j=parseInt(I.borderRightWidth,10),U=parseInt(I.borderBottomWidth,10),Z=0,B=0,Y="offsetWidth"in F?F.offsetWidth-F.clientWidth-W-j:0,$="offsetHeight"in F?F.offsetHeight-F.clientHeight-N-U:0,z="offsetWidth"in F?0===F.offsetWidth?0:V/F.offsetWidth:0,J="offsetHeight"in F?0===F.offsetHeight?0:C/F.offsetHeight:0;if(p===F)Z="start"===d?P:"end"===d?P-g:"nearest"===d?i(m,m+g,g,N,U,m+P,m+P+v,v):P-g/2,B="start"===s?A:"center"===s?A-D/2:"end"===s?A-D:i(H,H+D,D,W,j,H+A,H+A+T,T),Z=Math.max(0,Z+m),B=Math.max(0,B+H);else{Z="start"===d?P-L-N:"end"===d?P-O+U+$:"nearest"===d?i(L,O,C,N,U+$,P,P+v,v):P-(L+C/2)+$/2,B="start"===s?A-k-W:"center"===s?A-(k+V/2)+Y/2:"end"===s?A-_+j+Y:i(k,_,V,W,j+Y,A,A+T,T);var q=F.scrollLeft,K=F.scrollTop;P+=K-(Z=Math.max(0,Math.min(K+Z/J,F.scrollHeight-C/J+$))),A+=q-(B=Math.max(0,Math.min(q+B/z,F.scrollWidth-V/z+Y)))}x.push({el:F,top:Z,left:B})}return x}},605654:function(e,n,o){"use strict";o.d(n,{n:function(){return i}});var a=o(408625),t=o(222527),r=o(369011);function i(e,n,o){let i=(0,r.O)((o||{}).ignore||[]),d=function(e){let n=[];if(!Array.isArray(e))throw TypeError("Expected find and replace tuple or list of tuples");let o=!e[0]||Array.isArray(e[0])?e:[e],t=-1;for(;++t<o.length;){let e=o[t];n.push([function(e){return"string"==typeof e?RegExp((0,a.Z)(e),"g"):e}(e[0]),function(e){return"function"==typeof e?e:function(){return e}}(e[1])])}return n}(n),s=-1;for(;++s<d.length;)(0,t.S4)(e,"text",R);function R(e,n){let o,a=-1;for(;++a<n.length;){let e=n[a],t=o?o.children:void 0;if(i(e,t?t.indexOf(e):void 0,o))return;o=e}if(o)return function(e,n){let o=n[n.length-1],a=d[s][0],t=d[s][1],r=0,i=o.children.indexOf(e),R=!1,l=[];a.lastIndex=0;let c=a.exec(e.value);for(;c;){let o=c.index,i={index:c.index,input:c.input,stack:[...n,e]},d=t(...c,i);if("string"==typeof d&&(d=d.length>0?{type:"text",value:d}:void 0),!1===d?a.lastIndex=o+1:(r!==o&&l.push({type:"text",value:e.value.slice(r,o)}),Array.isArray(d)?l.push(...d):d&&l.push(d),r=o+c[0].length,R=!0),!a.global)break;c=a.exec(e.value)}return R?(r<e.value.length&&l.push({type:"text",value:e.value.slice(r)}),o.children.splice(i,1,...l)):l=[e],i+l.length}(e,n)}}},411038:function(e,n,o){"use strict";o.d(n,{e:function(){return R}});var a=o(110250),t=o(911114),r=o(66701),i=o(906508);let d={}.hasOwnProperty,s={};function R(e,n){let o=n||s,r=new Map,R=new Map,f=new Map,M={all:function(e){let n=[];if("children"in e){let o=e.children,a=-1;for(;++a<o.length;){let t=M.one(o[a],e);if(t){if(a&&"break"===o[a-1].type&&(!Array.isArray(t)&&"text"===t.type&&(t.value=p(t.value)),!Array.isArray(t)&&"element"===t.type)){let e=t.children[0];e&&"text"===e.type&&(e.value=p(e.value))}Array.isArray(t)?n.push(...t):n.push(t)}}}return n},applyData:c,definitionById:r,footnoteById:R,footnoteCounts:f,footnoteOrder:[],handlers:{...i.q,...o.handlers},one:function(e,n){let o=e.type,t=M.handlers[o];if(d.call(M.handlers,o)&&t)return t(M,e,n);if(M.options.passThrough&&M.options.passThrough.includes(o)){if("children"in e){let{children:n,...o}=e,t=(0,a.ZP)(o);return t.children=M.all(e),t}return(0,a.ZP)(e)}return(M.options.unknownHandler||u)(M,e,n)},options:o,patch:l,wrap:h};return(0,t.Vn)(e,function(e){if("definition"===e.type||"footnoteDefinition"===e.type){let n="definition"===e.type?r:R,o=String(e.identifier).toUpperCase();!n.has(o)&&n.set(o,e)}}),M}function l(e,n){e.position&&(n.position=(0,r.FK)(e))}function c(e,n){let o=n;if(e&&e.data){let n=e.data.hName,t=e.data.hChildren,r=e.data.hProperties;"string"==typeof n&&("element"===o.type?o.tagName=n:o={type:"element",tagName:n,properties:{},children:"children"in o?o.children:[o]}),"element"===o.type&&r&&Object.assign(o.properties,(0,a.ZP)(r)),"children"in o&&o.children&&null!=t&&(o.children=t)}return o}function u(e,n){let o=n.data||{},a="value"in n&&!(d.call(o,"hProperties")||d.call(o,"hChildren"))?{type:"text",value:n.value}:{type:"element",tagName:"div",properties:{},children:e.all(n)};return e.patch(n,a),e.applyData(n,a)}function h(e,n){let o=[],a=-1;for(n&&o.push({type:"text",value:"\n"});++a<e.length;)a&&o.push({type:"text",value:"\n"}),o.push(e[a]);return n&&e.length>0&&o.push({type:"text",value:"\n"}),o}function p(e){let n=0,o=e.charCodeAt(n);for(;9===o||32===o;)n++,o=e.charCodeAt(n);return e.slice(n)}},652183:function(e,n,o){"use strict";o.d(n,{g:function(){return i}});var a=o(453925),t=o(864060),r=o(327614);function i(e,n,o,i){let d=(0,a.c)(o),s=o.enter("emphasis"),R=o.createTracker(i),l=R.move(d),c=R.move(o.containerPhrasing(e,{after:d,before:l,...R.current()})),u=c.charCodeAt(0),h=(0,r.T)(i.before.charCodeAt(i.before.length-1),u,d);h.inside&&(c=(0,t.w)(u)+c.slice(1));let p=c.charCodeAt(c.length-1),f=(0,r.T)(i.after.charCodeAt(0),p,d);f.inside&&(c=c.slice(0,-1)+(0,t.w)(p));let M=R.move(d);return s(),o.attentionEncodeSurroundingInfo={after:f.outside,before:h.outside},l+c+M}i.peek=function(e,n,o){return o.options.emphasis||"*"}},182940:function(e,n,o){"use strict";o.d(n,{p:function(){return d}});var a=o(133753),t=o(622140),r=o(414064),i=o(19096);function d(e,n,o,d){let s=o.enter("list"),R=o.bulletCurrent,l=e.ordered?(0,r.l)(o):(0,a.g)(o),c=e.ordered?"."===l?")":".":(0,t.H)(o),u=!!n&&!!o.bulletLastUsed&&l===o.bulletLastUsed;if(!e.ordered){let n=e.children?e.children[0]:void 0;if(("*"===l||"-"===l)&&n&&(!n.children||!n.children[0])&&"list"===o.stack[o.stack.length-1]&&"listItem"===o.stack[o.stack.length-2]&&"list"===o.stack[o.stack.length-3]&&"listItem"===o.stack[o.stack.length-4]&&0===o.indexStack[o.indexStack.length-1]&&0===o.indexStack[o.indexStack.length-2]&&0===o.indexStack[o.indexStack.length-3]&&(u=!0),(0,i.T)(o)===l&&n){let n=-1;for(;++n<e.children.length;){let o=e.children[n];if(o&&"listItem"===o.type&&o.children&&o.children[0]&&"thematicBreak"===o.children[0].type){u=!0;break}}}}u&&(l=c),o.bulletCurrent=l;let h=o.containerFlow(e,d);return o.bulletLastUsed=l,o.bulletCurrent=R,s(),h}},685940:function(e,n,o){"use strict";o.d(n,{f:function(){return i}});var a=o(801873),t=o(864060),r=o(327614);function i(e,n,o,i){let d=(0,a.M)(o),s=o.enter("strong"),R=o.createTracker(i),l=R.move(d+d),c=R.move(o.containerPhrasing(e,{after:d,before:l,...R.current()})),u=c.charCodeAt(0),h=(0,r.T)(i.before.charCodeAt(i.before.length-1),u,d);h.inside&&(c=(0,t.w)(u)+c.slice(1));let p=c.charCodeAt(c.length-1),f=(0,r.T)(i.after.charCodeAt(0),p,d);f.inside&&(c=c.slice(0,-1)+(0,t.w)(p));let M=R.move(d+d);return s(),o.attentionEncodeSurroundingInfo={after:f.outside,before:h.outside},l+c+M}i.peek=function(e,n,o){return o.options.strong||"*"}},364410:function(e,n,o){"use strict";o.d(n,{L:function(){return t}});var a=o(574744);let t={name:"characterEscape",tokenize:function(e,n,o){return function(n){return e.enter("characterEscape"),e.enter("escapeMarker"),e.consume(n),e.exit("escapeMarker"),t};function t(t){return(0,a.sR)(t)?(e.enter("characterEscapeValue"),e.consume(t),e.exit("characterEscapeValue"),e.exit("characterEscape"),n):o(t)}}}},975350:function(e,n,o){"use strict";o.d(n,{k:function(){return i}});var a=o(577090),t=o(574744),r=o(108025);let i={resolve:function(e){return(0,r._)(e),e},tokenize:function(e,n){let o;return function(n){return e.enter("content"),o=e.enter("chunkContent",{contentType:"content"}),a(n)};function a(n){return null===n?r(n):(0,t.Ch)(n)?e.check(d,i,r)(n):(e.consume(n),a)}function r(o){return e.exit("chunkContent"),e.exit("content"),n(o)}function i(n){return e.consume(n),e.exit("chunkContent"),o.next=e.enter("chunkContent",{contentType:"content",previous:o}),o=o.next,a}}},d={partial:!0,tokenize:function(e,n,o){let r=this;return function(n){return e.exit("chunkContent"),e.enter("lineEnding"),e.consume(n),e.exit("lineEnding"),(0,a.f)(e,i,"linePrefix")};function i(a){if(null===a||(0,t.Ch)(a))return o(a);let i=r.events[r.events.length-1];return!r.parser.constructs.disable.null.includes("codeIndented")&&i&&"linePrefix"===i[1].type&&i[2].sliceSerialize(i[1],!0).length>=4?n(a):e.interrupt(r.parser.constructs.flow,o,n)(a)}}}},994052:function(e,n,o){"use strict";o.d(n,{C:function(){return a}});let a={name:"labelStartImage",resolveAll:o(354242).Z.resolveAll,tokenize:function(e,n,o){let a=this;return function(n){return e.enter("labelImage"),e.enter("labelImageMarker"),e.consume(n),e.exit("labelImageMarker"),t};function t(n){return 91===n?(e.enter("labelMarker"),e.consume(n),e.exit("labelMarker"),e.exit("labelImage"),r):o(n)}function r(e){return 94===e&&"_hiddenFootnoteSupport"in a.parser.constructs?o(e):n(e)}}}},881799:function(e,n,o){"use strict";o.d(n,{c:function(){return h},e:function(){return function e(n){let o=n.split("/");if(0===o.length)return[];let[a,...t]=o,r=a.endsWith("?"),i=a.replace(/\?$/,"");if(0===t.length)return r?[i,""]:[i];let d=e(t.join("/")),s=[];return s.push(...d.map(e=>""===e?i:[i,e].join("/"))),r&&s.push(...d),s.map(e=>n.startsWith("/")&&""===e?"/":e)}},f:function(){return function e(n){let o=arguments.length>1&&void 0!==arguments[1]?arguments[1]:[],a=arguments.length>2&&void 0!==arguments[2]?arguments[2]:[],t=arguments.length>3&&void 0!==arguments[3]?arguments[3]:"";return n.forEach((n,r)=>{let i={relativePath:n.path||"",caseSensitive:!0===n.caseSensitive,childrenIndex:r,route:n};i.relativePath.startsWith("/")&&(i.relativePath=i.relativePath.slice(t.length));let d=l([t,i.relativePath]),R=a.concat(i);if(n.children&&n.children.length>0&&e(n.children,o,R,d),null!=n.path||!!n.index)o.push({path:s(d),score:function(e,n){let o=e.split("/"),a=o.length;return o.some(u)&&(a+=-2),n&&(a+=2),o.filter(e=>!u(e)).reduce((e,n)=>e+(c.test(n)?3:""===n?1:10),a)}(d,n.index),routesMeta:R})}),o}},g:function(){return p},j:function(){return d}}),o(602960),o(141857),o(207418),o(847119),o(46163),o(295655),o(865629),o(596629),o(870128),o(65442),o(82020);let a=/\/$|\/\?/;function t(){let e=arguments.length>0&&void 0!==arguments[0]?arguments[0]:"",n=arguments.length>1&&void 0!==arguments[1]&&arguments[1];return n?a.test(e):e.endsWith("/")}function r(){let e=arguments.length>0&&void 0!==arguments[0]?arguments[0]:"";return(!function(){let e=arguments.length>0&&void 0!==arguments[0]?arguments[0]:"";return e.startsWith("/")}(e)?e:e.slice(1))||"/"}var i=function(){let e=arguments.length>0&&void 0!==arguments[0]?arguments[0]:"";return e.split("://").map(e=>e.replace(/\/{2,}/g,"/")).join("://")},d=function(e){for(var n=arguments.length,o=Array(n>1?n-1:0),a=1;a<n;a++)o[a-1]=arguments[a];let i=e||"";for(let e of o.filter(e=>{var n;return(n=e)&&"/"!==n}))i=i?function(){let e=arguments.length>0&&void 0!==arguments[0]?arguments[0]:"",n=arguments.length>1&&void 0!==arguments[1]&&arguments[1];if(!n)return e.endsWith("/")?e:e+"/";if(t(e,!0))return e||"/";let[o,...a]=e.split("?");return o+"/"+(a.length>0?`?${a.join("?")}`:"")}(i)+r(e):e;return i},s=function(){let e=arguments.length>0&&void 0!==arguments[0]?arguments[0]:"",n=arguments.length>1&&void 0!==arguments[1]&&arguments[1];if(!n)return(t(e)?e.slice(0,-1):e)||"/";if(!t(e,!0))return e||"/";let[o,...a]=e.split("?");return(o.slice(0,-1)||"/")+(a.length>0?`?${a.join("?")}`:"")};let R=/\//g,l=e=>e.join("/").replace(/\/\/+/g,"/"),c=/^:\w+$/,u=e=>"*"===e;function h(e){return(e.match(R)||[]).length}function p(e){let n=arguments.length>1&&void 0!==arguments[1]?arguments[1]:"";if(!e)return[];let o=new Set([]);for(let a of e){let{route:{path:e}}=a,t=i(r(`${n}/${null!=e?e:""}`));o.add(t),n=t}return Array.from(o=new Set(Array.from(o).map(e=>{let n=e.split("/");return(n=n.map(e=>e.startsWith(":")?e:e.toLowerCase())).join("/")}).sort((e,n)=>h(e)-h(n))))}},226376:function(e,n,o){"use strict";o.d(n,{z:function(){return a}});let a=["mdxFlowExpression","mdxJsxFlowElement","mdxJsxTextElement","mdxTextExpression","mdxjsEsm"]},87505:function(e,n,o){"use strict";o.d(n,{E:function(){return r}}),o(370483);var a=o(531109),t=o(383091);class r extends a.XY{compute(e,n){let o;let{cfg:t}=this,r=t.hasher.create(),i=a.Ic.create(),d=i.words,{keySize:s,iterations:R}=t;for(;d.length<s;){o&&r.update(o),o=r.update(e).finalize(n),r.reset();for(let e=1;e<R;e+=1)o=r.finalize(o),r.reset();i.concat(o)}return i.sigBytes=4*s,i}constructor(e){super(),this.cfg=Object.assign(new a.XY,{keySize:4,hasher:t.pt,iterations:1},e)}}}}]);