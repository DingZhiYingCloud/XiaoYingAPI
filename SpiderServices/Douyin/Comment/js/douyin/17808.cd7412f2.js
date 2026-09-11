/*! For license information please see 17808.cd7412f2.js.LICENSE.txt */
!function(e,t){"object"==typeof module&&"object"==typeof module.exports?t():"function"==typeof define&&define.amd?define([],t):(e="undefined"!=typeof globalThis?globalThis:e||self)&&t()}(this,function(){"use strict";"object"==typeof window&&(window.openRedirect={version:"1.2.20",webpackPluginVersion:"3.4.22",reportOnly:!1})}),!function(e,t){"object"==typeof exports&&"undefined"!=typeof module?t(exports):"function"==typeof define&&define.amd?define(["exports"],t):t((e="undefined"!=typeof globalThis?globalThis:e||self).xss={})}(this,function(e){"use strict";var t=function(){return(t=Object.assign||function(e){for(var t,r=1,o=arguments.length;r<o;r++)for(var n in t=arguments[r])Object.prototype.hasOwnProperty.call(t,n)&&(e[n]=t[n]);return e}).apply(this,arguments)};function r(e,t,r){if(r||2==arguments.length)for(var o,n=0,i=t.length;n<i;n++)!o&&n in t||(o||(o=Array.prototype.slice.call(t,0,n)),o[n]=t[n]);return e.concat(o||Array.prototype.slice.call(t))}var o=/[^a-zA-Z0-9\\_:.-]/gim,n=/</g,i=/>/g,a=/&#([a-zA-Z0-9]*);?/gim,c=/&quot;/g,s=/&colon;?/gim,G=/&newline;?/gim,l=/((j\s*a\s*v\s*a|v\s*b|l\s*i\s*v\s*e)\s*s\s*c\s*r\s*i\s*p\s*t\s*|m\s*o\s*c\s*h\s*a):/gi,u=/u\s*r\s*l\s*\(.*/gi,d=/e\s*x\s*p\s*r\s*e\s*s\s*s\s*i\s*o\s*n\s*\(.*/gi,T=/"/g,p=function(e){return e.replace(n,"&lt;").replace(i,"&gt;")},h={indexOf:function(e,t){var r,o;for(r=0,o=e.length;r<o;r++)if(e[r]===t)return r;return -1},forEach:function(e,t,r){var o,n;for(o=0,n=e.length;o<n;o++)t.call(r,e[o],o,e)},some:function(e,t,r){var o,n;for(o=0,n=e.length;o<n;o++)if(t.call(r,e[o],o,e))return!0;return!1},trim:function(e){return e.replace(/(^\s*)|(\s*$)/g,"")},includes:function(e,t){if("string"==typeof e)return -1!==e.indexOf(t);for(var r=0;r<e.length;r++)if(e[r]===t)return!0;return!1},spaceIndex:function(e){var t=/\s|\n|\t/.exec(e);return t?t.index:-1},uniq:function(e){for(var t={},r=[],o=0;o<e.length;o++)t[e[o]]||(r.push(e[o]),t[e[o]]=!0);return r},from:function(e){for(var t=[],r=0;r<e.length;r++)t.push(e[r]);return t},keys:function(e){var t=[];for(var r in e)t.push(r);return t}};function F(e){return null==e}function f(e){var t;return'"'===(t=e)[0]&&'"'===t[t.length-1]||"'"===t[0]&&"'"===t[t.length-1]?e.substr(1,e.length-2):e}function g(e){var t,r,o,n,i,a,c,s="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=",G="",l=0;for(e=function(e){e=e.replace(/rn/g,"n");for(var t="",r=0;r<e.length;r++){var o=e.charCodeAt(r);o<128?t+=String.fromCharCode(o):o>127&&o<2048?t+=String.fromCharCode(o>>6|192)+String.fromCharCode(63&o|128):t+=String.fromCharCode(o>>12|224)+String.fromCharCode(o>>6&63|128)+String.fromCharCode(63&o|128)}return t}(e);l<e.length;)n=(t=e.charCodeAt(l++))>>2,i=(3&t)<<4|(r=e.charCodeAt(l++))>>4,a=(15&r)<<2|(o=e.charCodeAt(l++))>>6,c=63&o,isNaN(r)?a=c=64:isNaN(o)&&(c=64),G=G+s.charAt(n)+s.charAt(i)+s.charAt(a)+s.charAt(c);return G}function X(e){var t,r,o,n,i,a,c="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=",s="",G=0;for(e=e.replace(/[^A-Za-z0-9+/=]/g,"");G<e.length;)t=c.indexOf(e.charAt(G++))<<2|(n=c.indexOf(e.charAt(G++)))>>4,r=(15&n)<<4|(i=c.indexOf(e.charAt(G++)))>>2,o=(3&i)<<6|(a=c.indexOf(e.charAt(G++))),s+=String.fromCharCode(t),64!==i&&(s+=String.fromCharCode(r)),64!==a&&(s+=String.fromCharCode(o));return function(e){for(var t="",r=0,o=0,n=0,i=0;r<e.length;)(o=e.charCodeAt(r))<128?(t+=String.fromCharCode(o),r++):o>191&&o<224?(t+=String.fromCharCode((31&o)<<6|63&(i=e.charCodeAt(r+1))),r+=2):(i=e.charCodeAt(r+1),t+=String.fromCharCode((15&o)<<12|(63&i)<<6|63&(n=e.charCodeAt(r+2))),r+=3);return t}(s)}function M(e,t,r){var o="",n=0,i=!1,a=!1,c=0,s=e.length,G="",l="";e:for(c=0;c<s;c++){var u=e.charAt(c);if(!1===i){if("<"===u){i=c;continue}}else if(!1===a){if("<"===u){o+=r(e.slice(n,c)),i=c,n=c;continue}if(">"===u||c===s-1){o+=r(e.slice(n,i)),G=function(e){var t,r=h.spaceIndex(e);return t=-1===r?e.slice(1,-1):e.slice(1,r+1),"/"===(t=h.trim(t).toLowerCase()).slice(0,1)&&(t=t.slice(1)),"/"===t.slice(-1)&&(t=t.slice(0,-1)),t}(l=e.slice(i,c+1)),o+=t(i,o.length,G,l,"</"===l.slice(0,2)),n=c+1,i=!1;continue}if('"'===u||"'"===u)for(var d=1,T=e.charAt(c-d);""===T.trim()||"="===T;){if("="===T){a=u;continue e}T=e.charAt(c-++d)}}else if(u===a){a=!1;continue}}return n<s&&(o+=r(e.substr(n))),o}function m(e,t){var r=0,n=0,i=[],a=!1,c=e.length;function s(e,r){if(!((e=(e=h.trim(e)).replace(o,"").toLowerCase()).length<1)){var n=t(e,r||"");n&&i.push(n)}}for(var G=0;G<c;G++){var l=e.charAt(G),u=void 0;if(!1!==a||"="!==l){if(!1===a||G!==n){if(/\s|\n|\t/.test(l)){if(e=e.replace(/\s|\n|\t/g," "),!1===a){if(-1===(u=function(e,t){for(;t<e.length;t++){var r=e[t];if(" "!==r)return"="===r?t:-1}return -1}(e,G))){s(h.trim(e.slice(r,G))),a=!1,r=G+1;continue}G=u-1;continue}if(-1===(u=function(e,t){for(;t>0;t--){var r=e[t];if(" "!==r)return"="===r?t:-1}return -1}(e,G-1))){s(a,f(h.trim(e.slice(r,G)))),a=!1,r=G+1;continue}}}else{if(-1===(u=e.indexOf(l,G+1)))break;s(a,h.trim(e.slice(n+1,u))),a=!1,r=(G=u)+1}}else a=e.slice(r,G),r=G+1,n='"'===e.charAt(r)||"'"===e.charAt(r)?r:function(e,t){for(;t<e.length;t++){var r=e[t];if(" "!==r)return"'"===r||'"'===r?t:-1}return -1}(e,G+1)}return r<e.length&&(!1===a?s(e.slice(r)):s(a,f(h.trim(e.slice(r))))),h.trim(i.join(" "))}function v(e,t,r){if(r=function(e){return e=function(e){for(var t="",r=0,o=e.length;r<o;r++)t+=32>e.charCodeAt(r)?" ":e.charAt(r);return h.trim(t)}(e=(e=(e=e.replace(c,'"')).replace(a,function(e,t){return"x"===t[0]||"X"===t[0]?String.fromCharCode(parseInt(t.substr(1),16)):String.fromCharCode(parseInt(t,10))})).replace(s,":").replace(G," "))}(r),"href"===t||"src"===t){if("#"===(r=h.trim(r)))return"#";if("http://"!==r.substr(0,7)&&"https://"!==r.substr(0,8)&&"mailto:"!==r.substr(0,7)&&"tel:"!==r.substr(0,4)&&"data:image/"!==r.substr(0,11)&&"ftp://"!==r.substr(0,6)&&"./"!==r.substr(0,2)&&"../"!==r.substr(0,3)&&"#"!==r[0]&&"/"!==r[0])return""}else if("background"===t){if(l.lastIndex=0,l.test(r))return""}else if("style"===t&&(d.lastIndex=0,d.test(r)||(u.lastIndex=0,u.test(r)&&(l.lastIndex=0,l.test(r)))))return"";return r=function(e){return e=p(e=e.replace(T,"&quot;"))}(r)}var y=function(e){return"string"==typeof e?e.replace(/'/g,'"').replace('=""',"").replace(/\s+/g,"").toLowerCase():""},b=function(){function e(e){var t=function(e){var t={};for(var r in e)t[r]=e[r];return t}(e||{});t.stripIgnoreTag&&(t.onIgnoreTag,t.onIgnoreTag=function(){return""}),t.whiteList={},t.onTag=function(){},t.onTagAttr=function(){},t.onIgnoreTag=function(){},t.onIgnoreTagAttr=function(){},t.safeAttrValue=v,t.escapeHtml=p,this.options=Object.assign(t,e)}return e.prototype.process=function(e){if(!(e=(e=e||"").toString()))return"";var t,r,o,n,i,a,c=this.options,s=c.whiteList,G=c.onTag,l=c.onIgnoreTag,u=c.onTagAttr,d=c.onIgnoreTagAttr,T=c.safeAttrValue,p=c.escapeHtml;c.stripBlankChar&&(e=(t=(t=e.split("")).filter(function(e){var t=e.charCodeAt(0);return!(127===t||t<=31&&10!==t&&13!==t)})).join("")),c.allowCommentTag||(e=function(e){for(var t="",r=0;r<e.length;){var o=e.indexOf("\x3c!--",r);if(-1===o){t+=e.slice(r);break}t+=e.slice(r,o);var n=e.indexOf("--\x3e",o);if(-1===n)break;r=n+3}return t}(e));var F=!1;c.stripIgnoreTagBody&&(r=c.stripIgnoreTagBody,"function"!=typeof(o=l)&&(o=function(){}),n=!Array.isArray(r),i=[],a=!1,l=(F={onIgnoreTag:function(e,t,c){var s;if(s=e,n||-1!==h.indexOf(r,s)){if(c.isClosing){var G="[/removed]",l=c.position+G.length;return i.push([!1!==a?a:c.position,l]),a=!1,G}return a||(a=c.position),"[removed]"}return o(e,t,c)},remove:function(e){var t="",r=0;return h.forEach(i,function(o){t+=e.slice(r,o[0]),r=o[1]}),t+=e.slice(r)}}).onIgnoreTag);var f=M(e,function(e,t,r,o,n){var i={sourcePosition:e,position:t,isClosing:n,isWhite:Object.prototype.hasOwnProperty.call(s,r)},a=G(r,o,i);if(null!=a)return a;if(i.isWhite){if(i.isClosing)return"</".concat(r,">");var c=function(e){var t=h.spaceIndex(e);if(-1===t)return{html:"",closing:"/"===e[e.length-2]};var r="/"===(e=h.trim(e.slice(t+1,-1)))[e.length-1];return r&&(e=h.trim(e.slice(0,-1))),{html:e,closing:r}}(o),F=s[r],f=m(c.html,function(e,t){var o=-1!==h.indexOf(F,e),n=u(r,e,t,o);return null==n?o?(t=T(r,e,t,null))?"".concat(e,'="').concat(t,'"'):e:null==(n=d(r,e,t,o))?void 0:n:n});return o="<".concat(r),f&&(o+=" ".concat(f)),c.closing&&(o+=" /"),o+=">"}return null==(a=l(r,o,i))?p(o):a},p);return F&&(f=F.remove(f)),f},e}(),E=Function("\nvar _checkXSS = function (it) {\n  return it && it.Math == Math && it;\n};\nreturn _checkXSS(typeof globalThis === 'object' && globalThis) ||\n_checkXSS(typeof window === 'object' && window) ||\n_checkXSS(typeof self === 'object' && self) ||\n_checkXSS(typeof global === 'object' && global) ||\nFunction('return this')();\n")(),R=new(function(){function e(){var e=this;this.batchData=[],this.uniqKeys=new Set,this.timeout=2e3,this.lock=!1,this.getSlardarBid=function(){var t,r,o="douyin_web";if(!h.includes(o,"bid"))return o;if(e.config&&e.config.bid)return e.config.bid;if(E&&E._xssBid)return E._xssBid;if(E&&E.slardar&&"function"==typeof E.slardar.config){var n=(E.slardar.config()||{}).bid;if(n)return n}if(E&&E.Slardar&&"function"==typeof E.Slardar.config){var i=(E.Slardar.config()||{}).bid;if(i)return i}return(null===(r=null===(t=null==E?void 0:E.Slardar)||void 0===t?void 0:t._baseParams)||void 0===r?void 0:r.bid)||"argus"},this.getConfigRegion=function(){var t;return h.includes("cn","region")?e.config&&e.config.region?e.config.region:((null===(t=null==E?void 0:E.gfdatav1)||void 0===t?void 0:t.region)||"cn").toLowerCase():"cn"},this.gerReportUrl=function(){var t={cn:X("aHR0cHM6Ly9tb24uemlqaWVhcGkuY29tL21vbml0b3JfYnJvd3Nlci9jb2xsZWN0L2JhdGNoL3NlY3VyaXR5Lz9iaWQ9"),boe:X("aHR0cHM6Ly9tb24uemlqaWVhcGkuY29tL21vbml0b3JfYnJvd3Nlci9jb2xsZWN0L2JhdGNoL3NlY3VyaXR5Lz9iaWQ9"),ttp:X("aHR0cHM6Ly9tb24udXMudGlrdG9rdi5jb20vbW9uaXRvcl9icm93c2VyL2NvbGxlY3QvYmF0Y2gvc2VjdXJpdHkvP2JpZD0="),va:X("aHR0cHM6Ly9tb24tdmEuYnl0ZW92ZXJzZWEuY29tL21vbml0b3JfYnJvd3Nlci9jb2xsZWN0L2JhdGNoL3NlY3VyaXR5Lz9iaWQ9"),maliva:X("aHR0cHM6Ly9tb24tdmEuYnl0ZW92ZXJzZWEuY29tL21vbml0b3JfYnJvd3Nlci9jb2xsZWN0L2JhdGNoL3NlY3VyaXR5Lz9iaWQ9"),sg:X("aHR0cHM6Ly9tb24tdmEuYnl0ZW92ZXJzZWEuY29tL21vbml0b3JfYnJvd3Nlci9jb2xsZWN0L2JhdGNoL3NlY3VyaXR5Lz9iaWQ9"),boei18n:X("aHR0cHM6Ly9tb24tdmEuYnl0ZW92ZXJzZWEuY29tL21vbml0b3JfYnJvd3Nlci9jb2xsZWN0L2JhdGNoL3NlY3VyaXR5Lz9iaWQ9")}[e.getConfigRegion()];if(t)return t+e.getSlardarBid()}}return e.prototype.setConfig=function(e){this.config=e},e.prototype.upload=function(){var e=this,t=this.gerReportUrl();!this.lock&&t&&0!==this.batchData.length&&(this.lock=!0,setTimeout(function(){var r=e.batchData.slice(0,100);e.batchData=e.batchData.slice(100),E.fetch(t,{method:"post",body:JSON.stringify(r),headers:{"Content-Type":"application/json"}}).catch(function(e){}),e.lock=!1,e.upload()},this.timeout))},e.prototype.generateKey=function(e){return e.collectKey?[e.collectMode,e.collectKey].join("___"):""},e.prototype.push=function(e){this.batchData.push(e),this.upload()},e.prototype.report=function(e){var t=this.generateKey(e);if(E.fetch&&e.collectKey){var r="object"==typeof window?window.location.href:"SSR";e.documentUrl=r;var o={age:Math.floor(Date.now()),type:"xss",url:r,body:e,"user-agent":""};"enforce"===e.disposition&&"SSR"!==r||(o.url=t),"SSR"===r&&(o.url="SSR___".concat(o.url),o.body.ssr=!0),this.push(o)}},e}()),S=function(e){for(var t=0,r=function(r){Array.isArray(e[r])?0===e[r].length?delete e[r]:(e[r]=h.from(h.uniq(e[r])),t+=e[r].length):0===h.keys(e[r]).length?delete e[r]:h.keys(e[r]).forEach(function(o){e[r][o]=h.from(h.uniq(e[r][o])),t+=e[r][o].length})},o=0,n=h.keys(e);o<n.length;o++)r(n[o]);return{count:t,ret:e}};function P(e,t){return R.setConfig(t),new b(t).process(e)}function Q(e){var t,r=(t=/\s|\n|\t/.exec(e))?t.index:-1;if(-1===r)return{html:"",closing:"/"===e[e.length-2]};var o="/"===(e=e.slice(r+1,-1).trim())[e.length-1];return o&&(e=e.slice(0,-1).trim()),{html:e,closing:o}}var O=function(e){return -1===(e=(e=(e=(e=e.replace(/&colon;/gi,":")).replace(/&tab;/gi,"")).replace(/&newline;/gi,"")).replace(/(\t|\n|\r)/g,"")).indexOf("&#")?e.trim().toLowerCase():e.trim().replace(/&#(?:(x)([0-9a-f]+)|([0-9]+));?/gi,function(e,t,r,o){return String.fromCharCode(t?parseInt(r,16):parseInt(o))}).replace(/(\t|\n|\r)/g,"").toLowerCase()};function w(e,t){if(void 0===e&&(e=""),"string"!=typeof e)return!0;if(e=O(e),h.includes(e,"base64")&&!function(e){if(""===e||""===e.trim())return!0;try{return!h.includes(e,"data:text/html;base64")}catch(e){return!0}}(e))return t&&t("data:text/html;base64"),!1;var r=["expression(","behavior:","view-source:"];if(h.some(r,function(t){return -1!==e.indexOf(t)}))return h.forEach(r,function(r){-1!==e.indexOf(r)&&t&&t(r)}),!1;var o=["data:application","data:javascript","data:text/html","data:texthtml"];if(h.some(o,function(t){return -1!==e.indexOf(t)}))return h.forEach(o,function(r){-1!==e.indexOf(r)&&t&&t(r)}),!1;if(e.indexOf("javascript:")>0)return t&&t("javascript:"),!1;if(/^javascript:/i.test(e)){var n=e.slice(11).replace(/\s/g,"").trim();return!!h.some(["void","void(0)","void0","false","undefined",";"],function(e){return e===n})||(t&&t("javascript:"),!1)}return!0}var L=function(e,t){var r,o,n="<%= isSaveValidUrl =>";if("string"!=typeof e||(o=Number("<%= urlLimit =>"),void 0!==r&&(o=r),"NaN"!==e.toString()&&-1!==o&&e.length>=o)||w(e,t))return e;try{if(!0===(n=JSON.parse(n))||"true"===n){var i=new URL(e);return i.origin+i.pathname}}catch(e){}return"#"};function A(e,t,o){if(void 0===e&&(e=""),void 0===t&&(t=[]),"string"!=typeof e)return!0;if(!w(e=O(e)))return!1;var n,i={url:(n=e.match(/^(?:([A-Za-z]+):)?(\/{0,3})([0-9.\-A-Za-z]+)(?::(\d+))?(?:\/([^?#]*))?(?:\?([^#]*))?(?:#(.*))?$/)||[])[0],scheme:n[1],slash:n[2],host:n[3],port:n[4],path:n[5],query:n[6],hash:n[7]},a=i.scheme,c=i.host;return o?!!o(e):!(!a||!c)&&(!h.includes(["http","https","file"],a)||("object"==typeof window&&window&&(t=r(r([],t,!0),[location.host],!1)),h.some(t,function(e){return!!(e instanceof RegExp&&e.test(c))||e===c})))}var I={a:["target","title","spellcheck","rel"],canvas:[],abbr:["title"],address:[],area:["shape","coords","alt"],article:[],aside:[],audio:["autoplay","controls","loop","preload"],b:[],bdi:["dir"],bdo:["dir"],big:[],blockquote:["cite"],br:[],caption:[],center:[],cite:[],code:[],col:["align","valign","span","width"],colgroup:["align","valign","span","width"],dd:[],del:["datetime"],details:["open"],div:["dir"],dl:[],dt:[],em:[],font:["color","size","face"],footer:[],h1:[],h2:[],h3:[],h4:[],h5:[],h6:[],header:[],hr:[],i:[],img:["alt","title","width","height","decoding"],ins:["datetime"],li:[],mark:[],nav:[],ol:["start"],p:[],pre:[],s:[],section:[],small:[],span:[],sub:[],sup:[],delete:[],form:[],strong:[],mask:["maskunits","x","y","width","height","fill"],table:["width","border","align","valign"],tbody:["align","valign"],td:["width","rowspan","colspan","align","valign"],tfoot:["align","valign"],th:["width","rowspan","colspan","align","valign"],thead:["align","valign"],tr:["rowspan","align","valign"],tt:[],u:[],ul:[],wbr:[],video:["autoplay","controls","loop","preload","height","width"],svg:["viewBox","version","xmlns","fill","width","height","stroke","stroke-width","style"],path:["d","fill","opacity","stroke","p-id","fill-rule","clip-rule","stroke-width","stroke-linecap","stroke-linejoin","fill-opacity","mask"],rect:["x","y","width","height","fill","stroke","rx"],g:[]},C={collect:null,initCollect:function(){this.collect={whiteList:{},filterProtocol:[]}},removeCollect:function(){var e=S(this.collect),t=e.count,r=e.ret;return this.collect=null,{collectKey:0===t?null:JSON.stringify(r),collectMode:"white"}},onIgnoreTagAttr:function(e,t,o){return e&&h.indexOf(["href","src"],t)>-1?C.domainWhiteList&&Array.isArray(C.domainWhiteList)&&C.domainWhiteList.length>0&&!A(o,r([],C.domainWhiteList,!0))?"":"".concat(t,'="').concat(L(o,function(e){var t;null===(t=C.collect)||void 0===t||t.filterProtocol.push(e)}),'"'):e&&(h.indexOf(["style","class","id"],t)>-1||t.indexOf("data-")>-1)?"".concat(t,'="').concat(o,'"'):(C.collect.whiteList[e]=C.collect.whiteList[e]||[],void C.collect.whiteList[e].push(t))},onIgnoreTag:function(e,t){if("style"===e)return t;M(t,function(e,t,r,o){m(Q(o).html.replace("/",""),function(e){C.collect.whiteList[r]=C.collect.whiteList[r]||[],C.collect.whiteList[r].push(e)})},p)},whiteList:I,mergeWhiteList:function(e){for(var t,r={},o=0,n=h.keys(I);o<n.length;o++)r[t=n[o]]=h.from(I[t]);for(var i=0,a=h.keys(e);i<a.length;i++)r[t=a[i]]=t in I?I[t].concat(e[t]):h.from(e[t]);return r},setWhiteList:function(e){for(var t=0,r=h.keys(e);t<r.length;t++){var o=r[t];this.whiteList[o]=o in I?I[o].concat(e[o]):h.from(e[o])}}};try{var x={},D="merge";h.includes(D,"override")&&(C.whiteList=x.whiteList),h.includes(D,"merge")&&C.setWhiteList(x.whiteList)}catch(e){}var _=function(e,t){for(var r={},o=0,n=h.keys(e);o<n.length;o++){var i=n[o];Array.isArray(e[i])?r[i]=h.from(e[i]):r[i]=_({},e[i])}for(var a=0,c=h.keys(t);a<c.length;a++)(i=c[a])in e?Array.isArray(e[i])?r[i]=e[i].concat(t[i]):r[i]=_(e[i],t[i]):Array.isArray(t[i])?r[i]=h.from(t[i]):r[i]=_({},t[i]);return r},N={blackList:{a:["folder"],meta:["content"],iframe:["srcdoc"],input:["pattern"],vmlframe:["xmlns"]},blackTags:["script","xml","embed","isindex","object","base","set","handler","animate","payload","import"],blackAttrs:["charset","ns","namespace","formaction","xlink:href","xmlns:xlink","handler","repeat","repeat-start","repeat-end"],blackAttrRegExps:[/^on/],filterList:{param:["value"],video:["poster"],form:["action"]},filterAttrs:["href","src","background","style","dynsrc","lowsrc","content"]};try{var k={};k.blackAttrRegExps&&(k.blackAttrRegExps=k.blackAttrRegExps.map(function(e){return new RegExp(e.toString().slice(1,e.toString().length-1))}));var K="merge";h.includes(K,"override")&&(N=k),h.includes(K,"merge")&&(N=_(N,k))}catch(e){}var j={mode:"black",whiteList:{},blackConfig:N,collect:null,initCollect:function(){j.collect={blackList:{},blackTags:[],blackAttrs:[],blackAttrRegExps:[],filterAttrs:[],filterList:{},filterProtocol:[]}},removeCollect:function(){var e=S(j.collect),t=e.count,r=e.ret;return j.collect=null,{collectKey:0===t?null:JSON.stringify(r),collectMode:"black"}},onIgnoreTag:function(e,t){var r;if(!h.includes(N.blackTags,e))return M(t,function(e,t,r,o,n){if(-1!==r.indexOf("/"))return p(o);if(n)return"</".concat(r,">");var i=Q(o),a=m(i.html,function(e,t){var o,n=0;if(N.blackList[r]&&h.includes(N.blackList[r],e)&&(j.collect.blackList[r]=j.collect.blackList[r]||[],j.collect.blackList[r].push(e),n++),N.blackAttrRegExps.length&&N.blackAttrRegExps.some(function(t){return t.test(e)})&&h.forEach(N.blackAttrRegExps,function(t){t.test(e)&&(j.collect.blackAttrRegExps.push("".concat(t.toString(),"->").concat(e)),n++)}),N.blackAttrs.length&&h.includes(N.blackAttrs,e)&&(N.blackAttrs.push(e),n++),!n){if(N.filterList&&N.filterList[r]&&h.includes(N.filterList[r],e)){var i=L(t,function(e){var t;null===(t=j.collect)||void 0===t||t.filterProtocol.push(e)});return i!==t&&(j.collect.filterList[r]=j.collect.filterList[r]||[],j.collect.filterList[r].push(e)),t?"".concat(e,"='").concat(i,"'"):e}return N.filterAttrs&&h.includes(N.filterAttrs,e)?((i=L(t,function(e){var t;null===(t=j.collect)||void 0===t||t.filterProtocol.push(e)}))!==t&&(null===(o=j.collect)||void 0===o||o.filterAttrs.push(e)),t?"".concat(e,"='").concat(i,"'"):e):t?"".concat(e,"='").concat(t,"'"):e}});return o="<".concat(r),a&&(o+=" ".concat(a)),i.closing&&(o+=" /"),o+=">"},p);null===(r=j.collect)||void 0===r||r.blackTags.push(e)}},U=function(e){var t=e.reportOnly,r=void 0===t||t,o=e.block;return r&&"all"===r?"report":("string"==typeof r&&("true"===r&&(r=!0),"false"===r&&(r=!1)),o?"enforce":r?"report":"enforce")},V=function(e){return function(r,o,n){if(!r||"string"!=typeof r)return r;var i=o;e===P&&(i=C).initCollect();var a=e(r,i);if(y(a)===y(r))return r;if(!n)return a;var c=n.logType,s=U(n),G=i.removeCollect();return R.report(t(t({type:c,disposition:s},G),{sourceText:g(r),filterText:g(a)})),"enforce"===s?a:r}},B=V(function(e,t){return void 0===t&&(t={}),t&&t.whiteList||(t.whiteList={a:["target","href","title"],abbr:["title"],address:[],area:["shape","coords","href","alt"],article:[],aside:[],audio:["autoplay","controls","crossorigin","loop","muted","preload","src"],b:[],bdi:["dir"],bdo:["dir"],big:[],blockquote:["cite"],br:[],caption:[],center:[],cite:[],code:[],col:["align","valign","span","width"],colgroup:["align","valign","span","width"],dd:[],del:["datetime"],details:["open"],div:[],dl:[],dt:[],em:[],figcaption:[],figure:[],font:["color","size","face"],footer:[],h1:[],h2:[],h3:[],h4:[],h5:[],h6:[],header:[],hr:[],i:[],img:["src","alt","title","width","height"],ins:["datetime"],li:[],mark:[],nav:[],ol:[],p:[],pre:[],s:[],section:[],small:[],span:[],sub:[],summary:[],sup:[],strong:[],strike:[],table:["width","border","align","valign"],tbody:["align","valign"],td:["width","rowspan","colspan","align","valign"],tfoot:["align","valign"],th:["width","rowspan","colspan","align","valign"],thead:["align","valign"],tr:["rowspan","align","valign"],tt:[],u:[],ul:[],video:["autoplay","controls","crossorigin","loop","muted","playsinline","poster","preload","src","height","width"]}),new b(t).process(e)}),z=V(P),H=function(e,t,r){var o=[],n=L(e,function(e){o.push(e)});if(n===e)return e;o=h.from(h.uniq(o));var i=t||r||{};if(!i)return n;var a=i.logType,c=U(r);return R.report({type:a,disposition:c,collectKey:o.join("___"),collectData:JSON.stringify(o),collectMode:"black",sourceText:g(e),filterText:g(n)}),"enforce"===c?n:e},Z=E._xssProject||{},W=E.xssNamespace||{},q="3.0.26",$={FilterXSS:b,version:q,webpackPluginVersion:"<%= webpackPluginVersion =>",reportOnly:"<%= reportOnly =>",filterXSS:B,_filterXSS:z,filterUrl:H,Config:C,BlackConfig:j,project:Z,setProjectName:function(e){Z[e]=this,E._xssProjectName=e}};W.douyin_web=$,E.xssNamespace=W,E.Math&&!E.Math.xssNamespace&&(E.Math.xssNamespace=W),Z[q]=$,E.globalThis=E,E.getFilterXss=function(){return void 0!==this._xssProjectName?this._xssProject[this._xssProjectName]:$},E.xss=$,E.isSafeUrl=A,E.isSafeDomain=A,E.isSafeProtocol=w,E._xssProject=Z,E._xssProjectName&&(Z[E._xssProjectName]=$);var Y=$.setProjectName.bind($);e.BlackConfig=j,e.Config=C,e.FilterXSS=b,e._filterXSS=z,e.filterUrl=H,e.filterXSS=B,e.isSafeDomain=A,e.isSafeProtocol=w,e.isSafeUrl=A,e.project=Z,e.setProjectName=Y,e.setXssNamespace=function(e){var t=e.appId,r=e.bid,o=e.region;W[t]=$;C.bid=r,C.region=o,C.enabled=!0},e.xssNamespace=W,Object.defineProperty(e,"__esModule",{value:!0})}),(self.webpackChunkdouyin_web=self.webpackChunkdouyin_web||[]).push([["17808"],{160018:function(e,t,r){"use strict";var o=r(703196),n=r(545727);let i=(0,n.A)(function(e){return o.createElement("svg",Object.assign({viewBox:"0 0 24 24",fill:"none",xmlns:"http://www.w3.org/2000/svg",width:"1em",height:"1em",focusable:!1,"aria-hidden":!0},e),o.createElement("path",{fillRule:"evenodd",clipRule:"evenodd",d:"M10 5V4h4v1h-4ZM8 5V3a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2h4a1 1 0 1 1 0 2h-1v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7H4a1 1 0 0 1 0-2h4Zm7 2H7v13h10V7h-2ZM9 9.5c0-.28.22-.5.5-.5h1c.28 0 .5.22.5.5v7a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1-.5-.5v-7Zm4 0c0-.28.22-.5.5-.5h1c.28 0 .5.22.5.5v7a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1-.5-.5v-7Z",fill:"currentColor"}))},"delete_stroked");t.Z=i},993283:function(e,t,r){"use strict";r.d(t,{D3:function(){return h},N6:function(){return X},Pw:function(){return g},mG:function(){return p},rJ:function(){return f},sW:function(){return F}});var o=r(352645),n=r(961982),i=r(823702),a=r(227683),c=r(489386),s=r(286903),G={},l={},u={},d=new WeakMap,T=!1,p=function(e,t,r,o){G[e]=t||"",l[e]=r||c.lS.default,o&&(u[e]=o)},h=function(e){delete G[e],delete l[e],delete u[e]},F=function(e,t){try{d.set(t,e)}catch(e){}},f=function(e,t,r){var o=document.querySelector('[data-container-id="'.concat(e,'"]'));if(!!o&&!!(0,i.En)(e))o.contentWindow.postMessage({type:"executeScript",script:t,callbackID:r},"*")},g=function(e){var t=document.querySelector('[data-container-id="'.concat(e,'"]'));if(!!t&&!!(0,i.En)(e))t.contentWindow.postMessage({type:"historyBack"},"*")},X=function(){if(!T)T=!0,addEventListener("message",function(e){var t=e.data||{};if(!t||"call_JSB"!==t.type)return;var r=d.get(e.source)||"";if(!r){var T=document.querySelectorAll('[data-container-id^="'.concat(s.TO,'"]')),p=!0,h=!1,F=void 0;try{for(var f,g=Array.from(T)[Symbol.iterator]();!(p=(f=g.next()).done);p=!0){var X=f.value;if(X.contentWindow===e.source){r=X.dataset.containerId||X.getAttribute("data-container-id")||"";try{X.contentWindow&&d.set(X.contentWindow,r)}catch(e){}break}}}catch(e){h=!0,F=e}finally{try{!p&&null!=g.return&&g.return()}finally{if(h)throw F}}}if(!!r&&!!(0,i.En)(r)){var M=t.methodName||"",m=Array.isArray(t.params)?t.params:[],v=t.callbackID,y=function(e){return 1===e.length&&e[0]&&"object"==typeof e[0]&&!Array.isArray(e[0])?e[0]:e.length>0?{args:e}:{}};if("on"===M||"once"===M){var b=m[0];"string"==typeof b&&null!=v&&(0,i.d8)(r,b,v,"once"===M);return}if("off"===M){var E,R=m[0],S=null!==(E=m[1])&&void 0!==E?E:v;"string"==typeof R&&(0,i.QZ)(r,R,S);return}if("trigger"===M){var P=m[0],Q=m[1];"string"==typeof P&&(0,o.a)({__msg_type:"event",__event_id:P,__params:Q},r);return}var O=M,w=y(m);"call"===M&&(O=m[0],w=y(m.slice(1)));var L=n.oT.get(r)||{},A={containerID:r,containerType:c.mC.WEBVIEW,globalProps:L,sendEvent:function(e,t){(0,o.a)({__msg_type:"event",__event_id:e,__params:t},r)},callback:function(e){var t=document.querySelector('[data-container-id="'.concat(r,'"]'));if(!!t)t.contentWindow.postMessage({type:"executeCallback",callbackID:v,params:e},"*")}};if(r in u&&u[r][O]){(0,a.pH)(u[r][O],{callbackId:String(v),name:O,params:w},A);return}var I=G[r]||"",C=l[r]||c.lS.default;(0,a.Xw)(I?[O,I].join(n.bA):O,{callbackId:String(v),name:O,params:w},A,C)}})}},659479:function(e,t,r){"use strict";r.d(t,{Z:function(){return n}});let o=`
GeForce RTX 4090|1950
GeForce RTX 4090 Laptop GPU|1791
GeForce RTX 4070 Ti|1517
GeForce RTX 3090 Ti|1465
GeForce RTX 4080|1426
GeForce RTX 4060 Laptop GPU|1408
GeForce RTX 3080 Ti Laptop GPU|1394
GeForce RTX 3080|1325
GeForce RTX 3080 Ti|1298
RTX A5500 Laptop GPU|1242
GeForce RTX 3090|1235
GeForce RTX 3070 Ti|1229
GeForce RTX 3070|1228
GeForce RTX 3060 Ti|1166
GeForce RTX 3080 Laptop GPU|1139
RTX A4000 Laptop GPU|1126
GeForce RTX 2080 Ti|1120
GeForce RTX 3070 Laptop GPU|1077
TITAN V|1070
GeForce RTX 2080 SUPER|1063
Quadro RTX 8000|1054
RTX A6000|1046
TITAN RTX|1046
GeForce RTX 3070 Ti Laptop GPU|1033
RTX A5000 Laptop GPU|1027
GeForce RTX 4090 Laptop GPU|1024
GeForce RTX 3060|1015
TITAN X (Pascal)|1008
TITAN Xp|995
GeForce GTX 1080 Ti|992
GeForce RTX 4070 Laptop GPU|989
GeForce RTX 4090|982
GeForce RTX 2070 SUPER|981
GeForce RTX 4080|975
GeForce RTX 3060|970
GeForce RTX 2080|970
GeForce RTX 4080 Laptop GPU|968
GeForce RTX 3060 Laptop GPU|913
GeForce RTX 2060 SUPER|890
GeForce RTX 4060 Laptop GPU|882
GeForce RTX 2070|879
GeForce RTX 2080 Super with Max-Q Design|868
GeForce RTX 2080 with Max-Q Design|868
Quadro RTX 5000|867
GeForce RTX 3080 Ti Laptop GPU|861
Quadro RTX 5000 with Max-Q Design|843
Asus GeForce GTX 1080|841
GeForce GTX 1080|841
GeForce RTX 2070 Super with Max-Q Design|837
RTX A3000 Laptop GPU|835
Quadro RTX 4000 with Max-Q Design|833
GeForce RTX 3070 Ti Laptop GPU|827
Quadro RTX 4000|817
RTX A6000|814
GeForce GTX 1070 Ti|785
GeForce RTX 4070 Ti|784
GeForce RTX 4050 Laptop GPU|784
RTX A5500 Laptop GPU|783
TITAN Xp COLLECTORS EDITION|771
GeForce RTX 2070 with Max-Q Design|765
GeForce RTX 3050|760
GeForce RTX 2060|757
GeForce GTX 980 Ti|755
Quadro P6000|753
GeForce GTX 1080|747
Quadro RTX 6000|744
GeForce GTX 1070|742
RTX A4000|739
GeForce RTX 3090|737
GeForce RTX 3080 Ti|733
GeForce GTX 1080 Ti|729
Quadro P4200|711
GeForce GTX 1080 with Max-Q Design|707
GeForce RTX 3060 Lite Hash Rate|705
EIZO MED-XN83|704
GeForce RTX 3080 Ti|701
GeForce GTX 1660 SUPER|701
TITAN Xp|700
EVGA GeForce GTX 1070|698
GeForce RTX 3090 Ti|696
Quadro GV100|695
Quadro P4000|695
GeForce GTX 1660 Ti|694
GeForce RTX 3070 Ti|690
RTX 6000 Ada Generation|687
GeForce RTX 3070|687
Quadro RTX 8000|685
RTX A2000 12GB|683
GeForce RTX 2080|679
GeForce GTX TITAN X|679
Quadro M6000 24GB|676
GeForce GTX 1660 SUPER|674
TITAN V|673
Quadro RTX 3000|672
Graphics Device|672
RTX A5000|669
GeForce RTX 3090|669
TITAN Xp COLLECTORS EDITION|669
GeForce GTX 1070 A17|668
GeForce RTX 3080 Laptop GPU|667
RTX A4500 Embedded GPU|663
RTX A5000 Laptop GPU|663
GeForce RTX 3080|658
GeForce RTX 3050 Ti Laptop GPU|657
GeForce GTX 1070 with Max-Q Design|656
GeForce RTX 3060 Ti|656
Quadro P4200 with Max-Q Design|651
GeForce RTX 3080|651
GeForce RTX 2080 SUPER|650
GeForce GTX 1070 Ti|648
GeForce GTX 1070 with MaxQ Design|642
RTX A3000 Laptop GPU|641
GeForce RTX 3070 Laptop GPU|641
GeForce GTX 1070|640
GA104GL [RTX A4000]|639
GeForce GTX 980 Ti|637
GeForce RTX 2070 Mobile / Max-Q Refresh|637
RTX A4000 Laptop GPU|634
GeForce RTX 3060|633
Microsoft Virtual Render Driver|633
GeForce RTX 3050 Laptop GPU|631
RTX A2000|629
GeForce RTX 2070 Mobile / Max-Q|626
GeForce RTX 3070|625
Quadro P5000|625
Quadro P4000|621
GeForce RTX 3060 Laptop GPU|621
GeForce RTX 2060 with Max-Q Design|618
GV102|614
GeForce RTX 2070 SUPER|612
GeForce GTX 1660|606
GeForce RTX 2070|604
GeForce GTX 1660 Ti with Max-Q Design|601
GeForce GTX TITAN X|598
RTX A2000 8GB Laptop GPU|598
GeForce GTX TITAN Xp|595
GeForce GTX 980|593
GeForce RTX 2080 SUPER|591
GTX 1060 HL|589
Tesla T4|589
GRID P4-1Q|585
RTX A4000|581
GeForce RTX 2080 Ti|577
GeForce RTX 2080 Super with Max-Q Design|576
Quadro RTX 4000 Mobile / Max-Q|576
TU102 [TITAN RTX]|574
GeForce GTX 1060 with Max-Q Design|571
GeForce RTX 2070 SUPER|570
GeForce GTX 1060 6GB|570
GeForce RTX 2080 Mobile|568
GeForce RTX 2060|568
Quadro P3200|565
P106-100|564
GRID V100DX-1Q|564
RTX A2000|562
GeForce RTX 2080 Ti Rev. A|561
GeForce RTX 2080 Rev. A|559
GV100 [TITAN V]|557
GeForce RTX 2080|556
GeForce GTX 1650 SUPER|554
P106-100 Custom|553
GeForce RTX 2070 Super with Max-Q Design|553
GV100|553
GeForce RTX 2070 Mobile|550
GP102 [TITAN X]|548
RTX A2000 12GB|546
GeForce GTX 1060 5GB|542
MSI GeForce GTX 1060|542
GeForce RTX 2060 SUPER|542
GRID T4-1Q|539
Quadro RTX 5000 Mobile / Max-Q|538
GeForce RTX 3050|538
GeForce GTX 1060 3GB|538
Quadro RTX 5000 with Max-Q Design|537
Quadro M6000|536
RTX A2000 Laptop GPU|536
GeForce GTX 1660 SUPER|533
A10-2B|530
TITAN X (Pascal)|530
Quadro P5000|527
GeForce RTX 2070|526
GeForce GTX 1080|525
GeForce RTX 2060 Mobile|524
PNY GeForce GTX 980|524
GeForce GTX 1080 Mobile|523
GeForce RTX 2060 SUPER|520
GeForce GTX 780 Ti|518
RTX A4500|516
GeForce RTX 2060 Rev. A|515
MSI GeForce GTX 980|515
Quadro P3200 with Max-Q Design|513
GeForce RTX 2070 with Max-Q Design|513
GeForce RTX 3050 Ti Laptop GPU|510
Quadro RTX 3000 Mobile / Max-Q|509
GeForce GTX 1660 SUPER|508
Quadro RTX 4000|508
GeForce GTX 1060|506
GeForce RTX 2080 with Max-Q Design|505
GeForce GTX 1080 Ti|505
GeForce GTX 1660 Ti Rev. A|504
GeForce GTX 1660 Ti Mobile|504
GeForce RTX 3050 Laptop GPU|503
GeForce RTX 2060|503
Quadro RTX 4000 with Max-Q Design|500
EIZO MED-XN83|499
GeForce GTX 970|499
GeForce GTX 1080|495
GeForce GTX 1070 Ti|492
GeForce GTX 980|491
A100-PCIE-40GB|489
GeForce GTX 1070|487
GeForce GTX 1660 Ti|487
Quadro P2200|485
GeForce GTX TITAN Black|484
TITAN Xp COLLECTORS EDITION|483
TITAN RTX|482
Quadro P5200|482
GeForce GTX 1060 with Max-Q Design|480
RTX A1000 Laptop GPU|479
GeForce GTX 1060 6GB|479
Quadro RTX 5000|475
TITAN V|475
GRID P100-4Q|474
EVGA GeForce GTX 970|472
GeForce GTX 1650 SUPER|471
GeForce GTX 1650 Ti|470
Quadro RTX 3000|470
Quadro M5000|469
Quadro RTX 3000 with Max-Q Design|468
GeForce GTX 980 Ti|467
GeForce GTX TITAN|467
Quadro P4200|466
GeForce GTX 1070 with Max-Q Design|466
Quadro M5000|466
GeForce GTX 1080 Ti|466
Tesla M60|462
GeForce GTX 1660|457
GeForce GTX 1660|455
GeForce RTX 2050|453
GeForce GTX 1060|453
GeForce RTX 2060 with Max-Q Design|453
Quadro P3200 with Max-Q Design|452
Quadro P4000|450
GeForce GTX 1060 3GB|449
GeForce GTX 1070|448
GeForce GTX 1060 6GB Rev. 2|447
Gigabyte GeForce GTX 780 Ti|447
TITAN Xp|444
GeForce GTX 980M|440
A10-4Q|439
GeForce GTX 1080 with Max-Q Design|437
GeForce GTX 1650 SUPER|435
Quadro P5000|435
Quadro P3000|434
RTX A6000|434
GeForce GTX 1060 3GB|433
GeForce GTX 1070 Ti|432
GeForce GTX 780|432
GeForce GTX 1060 Mobile|432
Gigabyte GeForce GTX 970|431
GeForce GTX TITAN Z|431
Quadro K6000|429
GeForce GTX 1650|425
GeForce GTX 970|421
Tesla K20m|420
Quadro GV100|419
Quadro P4000|419
Quadro P3200|417
GTX 1060 HL|415
RTX A2000 Laptop GPU|415
GeForce GTX 780 by St3Phl3|414
P102-100|412
T1200 Laptop GPU|412
GeForce GTX 780 Ti|411
GeForce GTX 1060 6GB|408
GeForce GTX 1650 Ti with Max-Q Design|407
Quadro T2000 with Max-Q Design|407
Quadro P2000|406
Quadro P2200|406
GeForce RTX 2060 Max-Q|405
GeForce GTX 1650 Ti Mobile|403
GeForce GTX 1060 Mobile 6GB|403
GeForce GTX 1060 with Max-Q Design|401
GeForce GTX 980|398
GeForce RTX 2070 Rev. A|397
GeForce GTX TITAN X|397
Tesla T4|395
Quadro P6000|394
GeForce GTX 1060 3GB|394
Quadro M5000|393
GeForce GTX 1060 with Max-Q Design|392
PNY GeForce GTX 970|392
Quadro T2000|391
Quadro T1000 with Max-Q Design|391
GRID P40-8Q|390
GeForce GTX 780 Rev. 2|389
Quadro GP100|387
GeForce GTX 980|387
P104-100|387
GeForce GTX 1650 Ti|386
GRID P40-4Q|384
GeForce GTX 780 Ti|383
Device|383
TU117M|381
Quadro P2000|380
Quadro RTX 6000|379
GeForce GTX 1070 Mobile|378
Quadro T1000|377
GeForce RTX 3070 Mobile / Max-Q|376
GeForce GTX 1060|376
GRID V100-1Q|375
GeForce GTX 780 Rev. 2|372
GeForce RTX 2050|370
GeForce GTX 770|370
GeForce GTX 970|368
GeForce GTX 1650 Ti|368
GRID T4-2B4|368
Asus GeForce GTX 780|366
P106-100|365
Quadro RTX 8000|365
GeForce GTX TITAN Black|365
GRID RTX6000-2Q|365
GeForce GTX TITAN Black|363
Quadro M4000|363
GeForce GTX 1060 6GB|362
Quadro P5000|361
GeForce GTX 1650|361
Quadro M5500|361
GeForce GTX 780|360
GeForce GTX 780|360
GeForce GTX 980M|358
GeForce GTX 1650|358
GeForce GTX 1050 Ti|357
Quadro P3200 Mobile|357
GeForce GTX 1650 with Max-Q Design|356
Tesla T4|356
Quadro P2000|356
GeForce GTX TITAN|355
GeForce GTX 970|355
GeForce GTX 980 Ti|354
GeForce GTX 1660 Ti with Max-Q Design|354
GeForce GTX 780 Rev. 2|352
GRID P4-4Q|351
GeForce GTX TITAN X|351
T1200 Laptop GPU|350
GRID T4-8Q|350
GeForce GTX 1060|349
GeForce GTX 1050 Ti with Max-Q Design|348
GeForce GTX 970M|346
T1000 8GB|346
GeForce RTX 3080 Mobile / Max-Q 8GB/16GB|346
GeForce GTX 780 Ti|346
GeForce GTX 680|346
GeForce GTX 1660 Ti|345
GeForce GTX 780|345
Quadro M6000|344
GRID T4-16Q|344
GeForce RTX 2080 Ti|344
GRID T4-1B|343
Quadro K5200|342
Quadro P2200|341
T1000 8GB|341
Tesla K80|341
Quadro T2000 Mobile / Max-Q|338
TU107|337
GeForce GTX 780 Mac|336
GeForce GTX TITAN|336
GeForce GTX 980M|335
GRID P40-2Q|335
EVGA GeForce GTX 780|334
GeForce GTX TITAN Z|334
TITAN X (Pascal)|332
GeForce GTX 960|331
Tesla P40|331
GeForce GTX 1650 Ti with Max-Q Design|330
Tesla P40|330
GeForce GTX 1060se 3GB|329
GeForce GTX 1650 Mobile / Max-Q|329
Quadro T2000 with Max-Q Design|328
T1000|327
RTX A5500|326
A40-8Q|326
GeForce RTX 3060 Mobile / Max-Q|326
GeForce GTX 690|326
Tesla V100-SXM2-16GB|326
Quadro M5000|325
A16-2B|323
GeForce GTX 1050 Ti with Max-Q Design|321
GeForce GTX 1050 Ti Mobile|321
GeForce GTX 980M|319
Quadro M3000M|318
GeForce GTX 1650 with Max-Q Design|318
GeForce GTX 670|316
Quadro P3000|316
T600 Laptop GPU|315
Quadro T1000 with Max-Q Design|313
Tesla K80|312
Tesla K20m|311
GeForce GTX 770|311
Tesla P100-PCIE-16GB|311
Quadro M5000M|311
Tesla K80|309
EVGA GeForce GTX 1070|309
Quadro T1000|309
GeForce GTX 1050 Ti|309
GeForce GTX TITAN Z|308
Quadro T2000|308
Quadro M6000 24GB|308
GeForce GTX 760 Ti|308
GeForce RTX 2080 SUPER Mobile / Max-Q|308
GeForce GTX 1050 Ti|307
Quadro P2000|304
Quadro P6000|304
GeForce GTX 770 Mac Edition|303
MSi GeForce GTX 1050 Ti|303
A40|303
T600|303
P106-090|302
P106-090|301
Quadro K5200|300
GeForce GTX 770|299
GeForce GTX 680|299
GeForce GTX TITAN|299
GeForce GTX 680|297
GRID M60-4Q|296
Quadro M4000|296
GRID M60-2Q|295
GeForce GTX 760|294
GRID V100DX-16Q|293
Quadro RTX 6000/8000|293
GeForce GTX 770|293
GP104|292
GeForce GTX 780 Rev. 2|290
GeForce GTX 1050 Ti|288
GeForce GTX 950|288
EVGA GeForce GTX 1050 Ti|288
GeForce GTX 1650 with Max-Q Design|286
GeForce GTX 880M|285
%NVIDIA_DEV.13D7.0580.1028%|283
GP104GL|283
Gigabyte GeForce GTX 960|282
Quadro K5200|281
GeForce GTX 660 Ti|281
GeForce GTX 670|281
Quadro M4000|280
GeForce GTX 580|280
MSi GeForce GTX 960|280
Tesla M6|278
PNY GeForce GTX 680|278
T500|277
GeForce GTX 1050|276
GeForce GTX 1050 Ti with Max-Q Design|276
GeForce GTX 690|276
GeForce GTX 680|276
GeForce GTX 670|275
GeForce GTX 760 Ti|274
GeForce GTX 1050 3GB|272
GeForce GTX 880M|272
Tesla M60|272
Asus GeForce GTX 960|271
Quadro M4000|269
T600|268
Tesla K20m|268
GeForce GTX 760|268
GP102 [TITAN Xp]|267
GeForce GTX 960|267
GeForce GTX 670|265
Quadro T1000 Mobile|265
GeForce GTX 1050|264
Tesla M60|264
EVGA GeForce GTX 1080 Ti|263
GeForce GTX 970M|263
GeForce GTX 780M|262
GeForce GTX 690|262
Asus GeForce GTX 770|261
GeForce GTX 1070 with MaxQ Design|261
EVGA GeForce GTX 960|261
GeForce GTX 960|260
GRID T4-2Q|259
GeForce GTX 970M|259
GeForce GTX 960|259
Quadro M3000M|258
GeForce GTX 1060se 3GB|257
Tesla K10|257
Quadro M3000M|257
Quadro M2200|256
GeForce GTX 690|255
GeForce GTX 760|254
GeForce GTX 880M|254
Quadro K4200|253
Quadro P2000 with Max-Q Design|253
T550 Laptop GPU|253
Quadro K5200|252
MSI GeForce GTX 760|250
GeForce GTX 580|249
GeForce GTX 780M Mac Edition|249
GeForce GTX 570|249
Tesla V100-PCIE-16GB|248
GeForce GTX880M|248
GeForce GTX 760|247
GeForce GTX 570 Rev. 2|247
Asus GeForce GTX 670|246
GeForce GTX 580|246
GeForce GTX 1050|245
Tesla P4|244
GeForce GTX 680MX|244
GeForce GTX 480|242
GeForce GTX 1050|242
Quadro 7000|241
Quadro M4000M|241
GeForce GTX 1050 Mobile|240
GeForce GTX 660|240
GeForce GTX 760 (192-bit)|239
Quadro K5000|239
GeForce GTX 760 OEM|238
GeForce GTX 660 Ti|238
GeForce GTX 775M Mac Edition|238
GeForce GTX 965M|237
GeForce GTX 870M|236
GeForce GTX 950|236
GeForce GTX 560 Ti 448 Cores|236
GeForce GTX 780M|236
Quadro P2000 with Max-Q Design|234
MSI GeForce GTX 980 TI|234
GRID K2|233
GeForce GTX 1060 6GB OpenGL Engine|233
PNY GeForce GTX 1060|233
EVGA GeForce GTX 980|232
GRID RTX6000P-6Q|232
GeForce GTX 950|232
GeForce GTX 950|232
GeForce GTX 590|231
GeForce GTX 1070 OpenGL Engine|231
TITAN X (Pascal)|229
GeForce GTX 1050 with Max-Q Design|229
GeForce GTX TITAN Black|228
Quadro K4200|227
GeForce GTX 660 OEM|227
GeForce MX450|225
GeForce GTX 1050 with Max-Q Design|225
Quadro P1000|225
Graphics Device|225
Quadro M2000|222
GeForce GTX 1630|222
Quadro M4000M|221
Quadro K5100M|221
EVGA GeForce GTX 760|221
GeForce GTX 1070 Ti|221
GeForce GTX 660 Ti|220
GeForce GTX 570|220
GeForce GTX 660 Ti|219
Quadro K6000|219
GeForce GTX 570 Rev. 2|219
GeForce GTX 1050 with Max-Q Design|219
Tesla M40|218
GeForce GTX 680M|217
GeForce GTX 780M by Nick[D]vB|217
Asus GeForce GTX 980 TI|217
GeForce GTX 1060 3GB|217
Graphics Device|217
GeForce GTX 570 Rev. 2|216
GeForce GTX 1060 3GB OpenGL Engine|216
GeForce GTX 660|215
Point of View GeForce GTX 660 Ti|214
Gigabyte GeForce GTX 980|214
Quadro K5000|213
Quadro P1000|213
GeForce GTX 480|213
GeForce MX450|212
Quadro K4200|211
GRID K280Q|211
Asus GeForce GTX 760|210
Quadro P1000|210
GeForce GTX 680MX|209
GeForce GTX 1060 6GB|209
GeForce GTX 660|209
GeForce GTX 750 Ti|208
GeForce GTX 780M Mac Edition|208
GeForce GTX 775M Mac Edition|208
GRID K520|208
Quadro M2200|207
GRID M60-8Q|207
GRID K2|207
GeForce GTX 775M Mac Edition|206
GeForce GTX 560 Ti 448 Cores|205
GeForce GTX 760 (192-bit)|205
Quadro K5000|205
Gigabyte GeForce GTX 980 TI|204
GeForce GTX 780M Mac Edition|204
Asus GeForce GTX 660|204
GRID M60-1B|202
GeForce GTX 650 Ti BOOST|202
GeForce GTX 480|202
GeForce GTX 960M|201
GeForce GTX 660 OEM|201
GeForce GTX 780 Ti|201
Quadro K5000|201
GeForce GTX 780M Mac Edition|201
GeForce GTX 870M|200
GeForce GTX 680MX|200
GeForce GTX 680MX|199
Quadro P1000|198
Tesla P100 PCIe 16GB|198
Quadro K5100M|198
GeForce GTX 470|198
Quadro P620|197
Asus GeForce GTX 780|197
Quadro 6000|196
Quadro M1200|195
Quadro K2200|195
GeForce GTX 590|195
Quadro M2000M|194
Quadro M4000 OpenGL Engine|194
GeForce GTX 870M|194
GeForce GTX 1070|194
EVGA GeForce GTX 750 Ti|194
Zotac GeForce GTX 680|193
Quadro RTX 3000 with Max-Q Design|193
T400|193
Quadro M2200|193
Quadro K4100M by nikey22|192
GRID K2|192
GTX 865M by iMacGFX|191
Quadro M2000|191
GeForce GTX 980M|190
GeForce GTX 560 Ti|190
Palit GeForce GTX 660|190
GRID K260Q|189
GRID M10-2Q|189
GeForce GTX 660|189
GeForce GTX 965M|189
GeForce GTX 650 Ti BOOST|188
GeForce GTX 675MX Mac Edition|188
Quadro K5100M by nikey22|187
GeForce GTX 680M|187
Zotac GeForce GTX 660|186
GeForce GTX 650 Ti BOOST|186
GeForce GTX 760 (192-bit)|185
GRID M60-1Q|184
Gigabyte GeForce GTX 960|184
Quadro M2000M Special Edition|184
GeForce GTX 560 Ti|184
Inno3D GeForce GTX660|183
GeForce GTX 1060|183
GeForce GTX 675MX Mac Edition|182
Quadro P600|181
GeForce GTX 1080|181
GeForce GTX 675MX Mac Edition|181
Quadro P620|180
GK104 Board - 20530501|180
Ashley|180
Quadro M2000|179
GeForce GTX 860M|179
MSi GeForce GTX 1050 Ti|179
Asus GeForce GTX 750 Ti|178
GeForce GTX 750 Ti|178
GeForce GTX 750 Ti|177
EVGA GeForce GTX 980 TI|177
Asus GeForce GTX 770|177
GeForce GTX 760 OEM|176
GeForce GTX 750|176
Quadro P2000 Mobile|176
Quadro K4100M|175
T400 4GB|174
GeForce GTX 1080 Ti OpenGL Engine|174
Quadro K5000M|173
GeForce GTX 960A|173
GeForce GTX 560 Ti|172
Tesla M10|172
GeForce GTX 1080 Ti|172
GRID RTX6000P-6|172
GK104 Board - 2051b502|172
GeForce GTX 770M|172
GeForce GTX 960M|172
GeForce GTX 970|172
GRID M10-2Q|171
GeForce GTX 560 Ti OEM|171
MSi GeForce GTX 970|171
GK104GL [GRID K2]|171
GeForce GTX 470|170
GeForce GTX 560 Ti|170
TITAN Xp|170
GeForce GTX 870M|170
GeForce MX350|169
MSi GeForce GTX 580|169
GeForce GTX 960M|169
EVGA GeForce GTX 760|169
Quadro K4000M|169
T400|169
GeForce MX350|168
GeForce GTX 470|168
GeForce GTX 560|167
Quadro 6000|167
GeForce GTX 1050 Ti OpenGL Engine|167
Quadro M1200|167
Gigabyte GeForce GTX 970|166
GeForce GT 1030|166
GeForce GTX780M by nikey22|166
GeForce GTX870M by nikey22|166
Tesla V100-PCIE-32GB|165
Quadro K2200|165
Quadro M1000M|165
Quadro K2200|165
Asus GeForce GTX 970|164
GeForce GTX 750 Ti|164
Quadro M2000M|164
GeForce GTX 1050|164
GeForce GTX 1050 Ti|163
Quadro K5000|163
Graphics Device|162
GeForce MX250|162
T500|161
EVGA GeForce GTX 570|161
Quadro M2000M|161
Quadro K1200|159
GeForce GTX 860M|159
GeForce GTX 770M|159
Quadro M1200|158
GeForce GTX 675MX|158
GeForce MX330|158
Quadro K2200M|157
Quadro K4000|157
GeForce GTX 690|157
GeForce GTX 860M|157
MSi GeForce GTX 670|156
Quadro K2200|156
Quadro K4100M|156
GeForce GTX 770M by Nick[D]vB|155
Tesla V100-SXM2-32GB|155
GeForce GTX 1080 OpenGL Engine|155
Gigabyte GeForce GTX 670|155
EVGA GeForce GTX 960|155
GeForce GTX 750|155
GeForce Pre-Release TITAN X (Pascal) OpenGL Engine|154
GeForce GTX TITAN Xp|154
Asus GeForce GTX 950|154
Quadro K4100M|153
GeForce GTX 960|153
GeForce GTX 770M|153
GeForce MX330|153
Quadro M2200 Mobile|153
GeForce MX250|153
GeForce Pre-Release TITAN Xp OpenGL Engine|153
Quadro P600|153
Quadro M620|152
GeForce GTX 1070 Ti OpenGL Engine|152
GeForce GTX 770|152
GeForce GT 1030|152
Tesla C2070|152
GeForce GTX 650 Ti|152
GRID K240Q|151
GeForce GTX 480 OpenGL Engine|151
GeForce GTX 750|151
GeForce GTX TITAN|151
GeForce GTX 760 (192-bit)|151
GeForce GTX 560|151
GeForce GT 1030|151
Quadro K5000M|151
Quadro P1000 Mobile|151
Zotac GeForce GTX 660|151
GeForce GTX 460 v2|150
GRID GTX P40-6|150
MSi GeForce GTX 660|149
GeForce GTX 780M|149
MSI GeForce GTX 760|149
P106-090|149
GeForce GTX 950A|149
GeForce MX150|149
Asus GeForce GTX 1060|149
Unknown|149
GeForce GTX 980 Ti|148
GRID T4-4Q|148
GeForce GTX 465|147
Colorful GeForce GTX 960|147
Gigabyte GeForce GTX 750|147
Quadro M1000M|147
GeForce GTX 780 Mac|147
GeForce GTX 460|146
MSi GeForce GTX 960|146
GeForce GTX 560|146
Quadro K4000|145
GeForce GTX 970M|145
Quadro M1000M|145
Unknown|145
GeForce GTX 980|144
GeForce GTX 950|144
GeForce GTX 675M|144
Zotac GeForce GTX 960|144
GeForce Pre-Release Graphics Device|144
GeForce GTX 670 OpenGL Engine|143
Quadro K4000|143
EVGA GeForce GTX 580|143
GeForce GTX 950M|143
GeForce GTX TITAN Black OpenGL Engine|142
GeForce GTX 760|142
Quadro 5000|142
MSI GeForce GTX 570 HD|142
GeForce Pre-Release TITAN Xp COLLECTORS EDITION OpenGL E|142
GeForce GTX 1050 OpenGL Engine|142
GeForce GTX TITAN X|142
GeForce GTX 880M|141
GV-N660OC-2GD|141
GeForce GTX 750|141
Quadro M5000M|140
GeForce GTX 970 OpenGL Engine|140
GeForce GTX 675MX|140
Asus GeForce GTX 760|140
Quadro P5000 OpenGL Engine|139
GeForce GTX 580|139
GeForce GTX 675MX|139
Zotac GeForce GTX 750|139
Quadro K1200|139
GeForce MX150|139
GeForce GTX 650 Ti|139
Quadro K1200|139
GeForce GTX 980 Ti OpenGL Engine|139
GeForce GTX 580M|138
Asus GeForce GTX 580|138
GeForce GTX 770 OpenGL Engine|138
GeForce GT 1010|138
GeForce GTX 780 Rev. 2|138
Quadro P2000 OpenGL Engine|138
GeForce MX250|138
Quadro K4000|137
GeForce GTX 460 v2|137
GeForce GTX 770M|137
Gigabyte GeForce GTX 570 HD|136
GeForce GTX 465|136
GeForce GTX 460 v2|136
GeForce GTX 670|136
GeForce GTX 590 OpenGL Engine|136
GeForce GTX 780|135
GeForce GTX TITAN Black|135
GeForce GTX 660 Ti|135
Zotac GeForce GTX 560 Ti|134
GeForce GTX 880M OpenGL Engine|134
GeForce GTX 650 Ti|134
GeForce GTX 760 OpenGL Engine|134
null Graphics Device|134
Quadro M620|133
GeForce GTX 780M Mac Edition|133
GeForce MX150|132
Asus GeForce GTX 570 HD|132
GeForce GTX 775M OpenGL Engine|132
GeForce GTX 850M|132
Asus GeForce GTX 570|132
Quadro K6000 OpenGL Engine|131
GeForce GTX 850M|131
GeForce GTX 460|131
GeForce GTX 950A|130
GeForce GTX 780M OpenGL Engine|130
Point of View GeForce GTX 660 Ti|130
GeForce GTX 775M Mac Edition|130
EVGA GeForce GTX 650 Ti|130
EVGA GeForce GTX 750 Ti|129
GeForce GTX 460|129
Quadro P520|129
Gainward GeForce GTX 570|129
Asus GeForce GTX 750 Ti|129
Quadro K3100M|128
Quadro K2200|128
Asus GeForce GTX 560 Ti|127
GeForce GTX 680|127
GeForce GTX 680 OpenGL Engine|127
GeForce GTX 950M|127
GRID V100-2B|127
Gigabyte GeForce GTX 660 Ti|127
N15E-GT|126
Quadro K1200|126
GeForce GTX 650 Ti|126
Gigabyte GeForce GTX 770|126
GeForce GTX 660|126
Quadro 5000|125
GeForce GT 1030|125
GeForce GTX 950M|125
GeForce GTX 765M|125
Quadro M5000|125
Gigabyte GeForce GTX 560 Ti|125
GeForce GTX 580M|125
Quadro M2000|124
GeForce GTX 850M|124
GeForce GTX 570 OpenGL Engine|123
Gainward GeForce GTX 750 Ti|123
Quadro K2200M|123
GeForce GTX 780M Mac Edition|123
GeForce GTX 680MX OpenGL Engine|123
Quadro K4200|123
GeForce GTX 460 OEM|122
GeForce GTX 670MX|122
MSi GeForce GTX 560 Ti|122
GeForce GTX 460 SE|122
Quadro M4000|122
GeForce GTX880M OpenGL Engine|122
Quadro P620|121
GeForce GTX 560 SE|121
GeForce GTX880M by nikey22|121
GeForce GTX 555|121
GeForce GTX 965M OpenGL Engine|121
GeForce GTX 850A|121
Quadro K5000 OpenGL Engine|120
GeForce GTX 580 OpenGL Engine|120
Quadro K3100M|120
GeForce GTX 650 Ti BOOST|119
GeForce GTX 570M|119
GeForce GTX 675MX OpenGL Engine|119
GeForce GTX 775M Mac Edition|119
Zotac GeForce GTX 1050 Ti|118
GeForce GTX 965M|117
Quadro M600M|117
GeForce GTX 780M by Nick[D]vB|117
GeForce GTX 460 SE|117
GeForce GTX 555|116
GeForce GTX 670M|116
Quadro K3000M|116
GeForce GTX 780 Ti OpenGL Engine|116
Quadro K4000M|115
GeForce GTX 860M|115
Asus GeForce GTX 660|115
Tesla C2075|114
GeForce GTX 675MX Mac Edition|114
Zotac GeForce GTX 770|114
Gigabyte GeForce GTX 750 Ti|114
GeForce MX330|114
GeForce GT 1030|113
GeForce GTX TITAN OpenGL Engine|113
GeForce GTX 590|113
Quadro K620|113
GeForce GTX 780M|112
GeForce GTX 560 Ti|112
Quadro 6000|112
EVGA GeForce GTX 560 Ti|112
Asus GeForce GTX 960|112
Quadro K5000|112
Point of View GeForce GTX 470|111
PNY GeForce GTX 580|111
GeForce GTX 770M|111
GeForce GT 120|111
MSi GeForce GTX 660|111
Gigabyte GeForce GTX 560|111
GeForce GTX 680MX|110
GeForce 945M|110
GeForce GTX 765M|110
GeForce GTX 950 OpenGL Engine|110
GeForce Pre-Release Tesla C2075 OpenGL Engine|109
GeForce GTX 550 Ti|109
GeForce GTX 765M|108
PNY GeForce GTX 750|108
GeForce GTX 560 Ti 448 Cores|108
Quadro P500|108
GeForce GTX 670MX|108
GeForce GTX 680MX|107
GeForce GTX 460 SE|107
GeForce GTX 675MX Mac Edition|107
GeForce GTX 770M OpenGL Engine|107
GeForce 945M|107
GeForce GTX 675MX|107
PNY GeForce GTX 570 HD|106
GeForce GTX 745|106
GeForce MX230|106
GeForce GTX 670MX|106
GeForce 845M|106
Quadro K3100M OpenGL Engine|105
Quadro P2000|105
GeForce MX570 A|105
GeForce GTX 750 Ti|104
GeForce GTX 660 OEM|104
Quadro M600M|104
GeForce GTX 750|104
GeForce GTX 645|104
GP108|104
Quadro P520|104
Zotac GeForce GTX 460|103
Chip Model|103
GeForce GTX 670M|103
Quadro T1000|103
GeForce GTX 670M|103
GeForce GTX 650|103
Zotac GeForce GTX 750|102
GeForce GTX 460 OpenGL Engine|102
GeForce GTX 860M OpenGL Engine|102
Quadro 4000|102
Asus GeForce GTX 480|102
Zotac GeForce GTX 650 Ti|102
GeForce GT 755M|101
GF100 Board - 10220000|101
GeForce GTX 470M|101
GeForce GTX 570 Rev. 2|101
GeForce GTX 775M by iDopt Mac|101
GeForce GTX 765M by Nick[D]vB|101
GeForce GTX 570|101
GeForce GTX 645|101
GeForce GTX 550 Ti|100
GeForce GTX 760M|100
GeForce GT 1030 OpenGL Engine|100
GeForce GTX 650|100
Quadro P400|100
GeForce GTX 480|99
EVGA GeForce GTX 650|99
EVGA GeForce GTX 560|99
GeForce MX130|99
GeForce MX130|98
Asus GeForce GTX 460|98
Elitegroup GeForce GTX 460|98
Tesla V100-SXM2-32GB|98
GeForce GT 755M|98
GeForce GTX 760 Ti OpenGL Engine|98
Quadro P520|97
GeForce GT 755M Mac Edition|97
GeForce GTX 1060 5GB|97
Palit GeForce GTX 650 Ti|97
MSi GeForce GTX 460|96
GeForce GTX 650|96
Gigabyte GeForce GTX 580|96
Gigabyte GeForce GTX 460|96
GeForce GTX 745|96
EVGA GeForce GTX 550 Ti|96
GeForce GTX 465|96
GeForce GTX 460 SE|96
GeForce GTX 765M|96
GeForce GT 755M Mac Edition|96
Quadro M520|95
Quadro K620|95
T1000|95
GeForce GTX 745|95
Quadro K620|95
GeForce GT 755M|94
GeForce GTX 660 Ti OpenGL Engine|94
Quadro K3000M|94
Quadro K4000|94
Quadro K4000 OpenGL Engine|94
GeForce GTX 560|94
GeForce GTX 650 Ti OpenGL Engine|94
Zotac GeForce GTX 560|94
Asus GeForce GTX 560|93
GeForce GTX 650 Ti|93
GeForce GPU|92
GeForce GTX 460|92
MSi GeForce GTX 650 Ti|92
GeForce GTX 645|92
Gigabyte GeForce GTX 760|92
GeForce GTX 660M|92
GeForce GTS 450|92
GeForce GTX 765M|92
Quadro K2000D|92
Quadro K2000|91
GeForce GT 740|91
GeForce GTX 650|91
GRID M6-0B|91
HP Quadro K620|91
GeForce MX130|91
Quadro K3000M by ST3PHL3|91
Quadro 4000|90
GeForce MX230|90
Quadro K620|90
Quadro K2100M by Nick[D]vB|90
Quadro K3000M by nikey22|89
GeForce GT 650M OpenGL Engine|89
Quadro 4000|89
Quadro K3000M|88
GeForce GTX 660M|88
Quadro K6000|87
GeForce GT 755M Mac Edition|87
Palit GeForce GTX 650|87
Quadro P500|87
GeForce GTX 570M|86
Gainward GeForce GTX 460|86
GeForce GTX 950M|86
Quadro K2000D|86
GeForce GTX 650 Ti BOOST|86
Quadro K2100M|86
GeForce GTX 470|85
Quadro K2000|85
Quadro K2000|85
GeForce GT 750M Mac Edition|85
GeForce GTX 745|85
GRID K220Q|85
GeForce GTX 750 OpenGL Engine|85
Quadro 5000M|84
Quadro P400|84
GeForce GTS 450|84
GeForce GT 640 Rev. 2|84
GeForce GTX 660M Mac Edition|84
Quadro P400|84
Asus GeForce GTX 560 SE|84
PNY GeForce GTX 460|83
GeForce GT 640 Rev. 2|83
GeForce GTS 450 Rev. 2|83
GeForce GTS 450|83
GeForce GTS 450 Rev. 2|83
GeForce GTX 645|82
GeForce GPU|82
GeForce GTX 560M|82
Quadro K3000M|82
Quadro K2100M by nikey22|82
Gigabyte GeForce GTX 750|82
GeForce GT 740|82
GeForce GT 750M Mac Edition|82
GeForce GTX 765M OpenGL Engine|82
GeForce GTX 645 OpenGL Engine|82
Quadro K620|81
GeForce GTX 550 Ti OpenGL Engine|81
Quadro 4000M|81
PNY GeForce GTX 550 Ti|81
GeForce MX110|80
GeForce GTX 760M|80
MSi GeForce GTX 745|80
Quadro K2100M OpenGL Engine|80
Quadro K2000|80
Quadro 5000|80
Quadro K620 OpenGL Engine|80
MSi GeForce GTX 745|80
GeForce GT 755M OpenGL Engine|80
GeForce GTX 660M|79
Gigabyte GeForce GTX 550 Ti|79
MSi GeForce GTX 650|79
GeForce GTX 560M|79
Quadro P400|78
Quadro K2100M|78
Quadro K2100M|78
Zotac GeForce GTX 1050 Ti|78
Quadro 3000M|77
GeForce 940A|77
GeForce GTX 460M|77
GeForce GTX 550 Ti|77
GeForce GT 545|77
GeForce GT 650M Mac Edition|77
GeForce 940MX|76
GeForce GTX 650 OEM|76
GeForce GTX 550 Ti|76
GeForce GT 755M Mac Edition|76
GeForce GT 740 OpenGL Engine|75
Gainward GeForce GTX 550 Ti|75
Quadro K1200|75
GeForce GT 650M Mac Edition|75
EVGA GeForce GTX 650|75
GeForce GT 750M Mac Edition|74
GeForce GTX 745|73
GeForce GTX 555|73
GeForce GTX 650|73
Gainward GeForce GTS 450|73
GeForce GT 650M|73
GeForce GT 755M Mac Edition|73
GeForce GTX 460M|72
GeForce 930A|72
GeForce 930MX|72
GeForce 940MX|72
GeForce MX110|72
GeForce GT 750M Mac Edition|72
Quadro 2000|72
GeForce 845M|71
Quadro 2000D|71
GeForce GT 640 Rev. 2|71
GeForce MX110|71
GeForce GT 1010|71
GeForce GT 545|71
Quadro K1200 OpenGL Engine|71
GeForce 940MX|71
GeForce GTX 650 OpenGL Engine|71
EVGA GeForce GTX 650 Ti BOOST|71
Quadro K2100M|70
GeForce GT 1010|70
Quadro M500M|70
GeForce GT 650M Mac Edition|70
GeForce GT 640 OEM|70
Quadro K2000D|70
Quadro K2000 OpenGL Engine|70
GeForce GT 750M Mac Edition|70
GeForce GT 650M|69
Quadro K1100M by Nick[D]vB|69
GeForce GT 650M|69
GeForce 940M|69
GeForce GT 650M|69
Quadro 4000|69
GeForce GT 650M Mac Edition|69
GeForce GT 745M|69
Gainward GeForce GTX 560 Ti|68
GeForce 920MX|68
Quadro M520|68
GeForce GT 640|68
GeForce 840M|68
GeForce 9800 GTX / 9800 GTX+|68
GeForce GTX 770M by Nick[D]vB|67
Zotac GeForce GTX 650|67
Asus GeForce GTX 550 Ti|67
GeForce GT 750M|67
Quadro K3100M by nikey22|67
GeForce GT 750M|67
GeForce GTX 760 (192-bit) OpenGL Engine|67
HP Quadro 4000|67
Quadro K2000|67
GeForce GTS 450 Rev. 2|67
GeForce 930MX|67
GeForce GTX 660M Mac Edition|66
GeForce GTX 570|66
GeForce GT 750M|66
GeForce GT 650M Mac Edition|66
GeForce GT 650M OpenGL Engine|65
GeForce GTX 660M OpenGL Engine|65
GeForce 930M|65
Palit GeForce GTX 650|65
GeForce GTX 760M|65
GeForce GT 650M Mac Edition|65
GeForce 940M|65
GeForce GT 750M Mac Edition|64
GeForce 940M|64
GeForce GT 740|63
GeForce 930MX|63
Quadro 3000M|63
GeForce GT 730|63
Quadro K1100M|63
GeForce GT 750M|63
GeForce 840M|63
GeForce GT 640 OEM|63
GeForce 840M|63
GeForce GT 640 Rev. 2|62
GeForce GTS 450|62
Quadro 2000|62
GeForce GT 745M|62
GeForce GT 740|62
GeForce GT 640|62
Quadro 2000|62
GeForce GTX 660M Mac Edition|62
Quadro K1100M OpenGL Engine|62
Quadro K2000M|62
GeForce GTX 680MX OpenGL Engine|61
EVGA GeForce GT 730|61
Quadro 2000D|61
GeForce 840A|61
MSi GeForce GTX 660 Ti|61
Quadro K1100M|61
GeForce GT 645M|61
GeForce GTX 780M OpenGL Engine|61
HP GeForce GT 730|61
Quadro K5000M OpenGL Engine|61
EVGA GeForce GT 640|61
GeForce 920MX|60
Quadro M500M|60
Quadro K620M|60
GeForce 930M|60
GeForce 930A|60
GeForce GT 640 OEM|60
GeForce GT 640|60
Quadro 2000M|60
GeForce GT 640|60
GeForce GT 640M Mac Edition|60
GeForce GT 640M Mac Edition|60
GeForce GT 640M Mac Edition|59
GeForce GT 645M|59
GeForce 930M|59
Gigabyte GeForce GTX 650 Ti|59
GeForce GT 640 OEM|59
GeForce 830M|59
Asus GeForce GT 640|58
MSI GeForce GTX 1070|58
GeForce GT 555M|58
Quadro K2000M|58
Quadro K1100M|57
GeForce GT 650M Mac Edition|57
Quadro K2000M by Nick[D]vB|57
EVGA GeForce GTX 650 Ti|57
GeForce GT 640M|56
GeForce GT 650M Mac Edition|56
GeForce GT 445M|56
GeForce 830A|56
GeForce 9800 GT|56
Asus GeForce GTS 450|55
GeForce 830M|55
GeForce 920MX|55
Quadro 2000|55
EVGA GeForce GT 545|54
Quadro K2000M|54
GeForce GT 650M Mac Edition|54
GeForce GTX 280|54
GeForce GT 640|53
Quadro FX 2800M|53
Quadro 3000M OpenGL Engine|53
GeForce GT 740|53
null GeForce 920A|53
GeForce GT 640M Mac Edition|52
GeForce GT 635|52
Graphics Device|52
GeForce GT 640M|52
GeForce GTX 660M Mac Edition|52
Quadro 2000M|52
Quadro 5010M|52
GeForce GTS 250|52
GeForce GT 445M|51
GeForce GT 640M OpenGL Engine|51
GeForce GT 640M|50
EVGA GeForce GT 740|50
GeForce GT 640M Mac Edition|50
GeForce 730A|50
GeForce 920M|49
HP Quadro 2000|49
GeForce GT 730M|49
null GeForce 920A|49
GeForce GT 555M|49
GeForce GT 640M LE|49
GeForce GT 730M|49
GeForce GT 730M|48
GeForce GT 640M Mac Edition|48
Quadro K2000M OpenGL Engine|48
GeForce GT 640M LE|48
GeForce GT 740M|47
GeForce GTX 460M|47
GeForce GT 440|47
GeForce GT 440|46
GeForce GT 640M Mac Edition|46
Quadro P400|46
GeForce GT 730|46
Dell Quadro 2000M|45
GeForce GT 740M|45
GeForce GT 740M|45
GeForce GTS 450 Rev. 2|45
GeForce 920M|45
GeForce 920M|45
GeForce 910M|44
GeForce GTX 680M|44
GeForce GT 730|44
Quadro 2000M|44
GeForce GT 635|43
GeForce GT 720 OpenGL Engine|43
GeForce GT 635|43
Quadro K5200 OpenGL Engine|43
Zotac GeForce GTX 650|43
GeForce GT 440|43
GeForce GT 435M|42
GeForce GT 735M|42
Gainward GeForce GT 630|42
Quadro 1000M|42
GeForce 820M|41
GeForce GTX 680M OpenGL Engine|41
MSI GeForce GT 635|41
GeForce 820A|41
Tesla M10|41
Asus GeForce GT 440|40
Asus GeForce GT 630|40
GeForce GT 820M|40
GeForce 910M|40
GeForce GT 820M|40
GeForce GT 730|40
GeForce GT 550M|40
GeForce GT 430|40
GeForce GT 540M|39
Asus GeForce GT 720|39
GeForce GT 630|39
GeForce GT 530|39
GeForce GT 635M|39
GeForce GT 620M/630M/635M/640M LE|39
NVS 5400M|39
Quadro K600|39
Quadro K610M|39
Asus GeForce GT 730|39
GeForce GT 630|39
GeForce GT 440|39
GeForce GT 630M|38
GeForce 820M|38
Quadro K420|38
Quadro K610M|38
GeForce GT 625M|38
Quadro K1000M|38
NVS 5200M|38
GRID K1|38
Quadro K600|38
Quadro K420|38
GeForce GT 630|38
Quadro K600|37
Quadro 600|37
HP Quadro 600|37
Quadro K1000M|37
Quadro K610M|37
GRID K180Q|37
GRID K160Q|37
GeForce GT 635M|37
Gigabyte GeForce GT 440|37
GeForce 820M|37
GeForce GT 530|37
GeForce GT 540M|37
GeForce GT 630 OEM|37
Quadro K610M by Nick[D]vB|37
NVS 510|37
GeForce GT 630M|37
Quadro 1000M|37
GeForce GT 540M|37
GeForce GT 530|37
Quadro K1100M|37
Quadro K620M|37
Quadro 1000M|36
GeForce GT 730|36
GeForce 820M|36
GeForce GT 430|36
GRID K1|36
GeForce GT 525M|36
NVS 5200M|36
NVS 510|36
Zotac GeForce GT 430|36
Quadro K600|36
Asus GeForce GT 730|36
HP Quadro K4000|35
GeForce GT 755M Mac Edition|35
GeForce GT 630|35
NVS 5400M|35
NVS 5400M|35
GeForce GT 640 OpenGL Engine|35
GeForce GT 625M|35
GeForce GT 630|35
GeForce GT 430|35
Quadro K600 OpenGL Engine|35
Quadro K1000M|35
Zotac GeForce GT 630|35
Gigabyte GeForce GT 630|35
GRID K140Q vGPU|35
GeForce GT 710M|35
GeForce GT 620M|35
GeForce GT 720M|34
GeForce 710M|34
Quadro 1000M,|34
Quadro K510M|34
GeForce 9400 GT|34
Quadro K1000M|34
GeForce GT 635M|34
Quadro K420|34
GRID K180Q|34
Asus GeForce GT 430|34
Quadro K4100M|34
Gigabyte GeForce GT 730|34
GeForce GT 620M|34
GeForce GT 525M|34
Quadro K420|34
Dell NVS 5200M|34
GeForce 710A|34
GeForce GT 425M|33
GeForce GT 710B|33
GeForce GT 525M|33
Quadro 600|33
GeForce GT 620M|33
Quadro K600|33
Quadro 600|33
GeForce 610M/710M/810M/820M / GT 620M/625M/630M/720M|33
MSI GeForce GT 730|33
GeForce GT 710|33
GeForce GT 435M|33
NVS 510|33
Asus GeForce GT 710|33
NVS 510|32
GeForce 710M|32
GeForce GT 720M|32
GeForce GT 730A|32
GeForce GT 710M|32
GIGABYTE GeForce GTX 660|31
EVGA GeForce GT 710|31
GeForce GT 710|31
GeForce GT 710|31
GeForce GT 425M|31
GeForce GT 720|31
EVGA GeForce GT 710|31
Quadro K1000M by Nick[D]vB|31
Asus GeForce GT 710|31
GeForce GT 720|31
GeForce GT 420M|30
GeForce GT 710|30
null Graphics Device|30
GeForce GT 240|30
GeForce 810M|29
GeForce GT 720M|29
GeForce GT 710|29
Quadro 600|29
GeForce 810M|29
GeForce GT 420M|28
Quadro 410|28
GeForce GTX 660M|28
MSI GeForce GT 710|28
GeForce GT 720|28
GeForce GT 735M|27
GeForce GT 720|27
GeForce GT 720|27
GeForce GT 630 OpenGL Engine|27
Quadro 410|27
GeForce GT 330M|26
GeForce GT 420M|26
GeForce GT 430|26
GeForce 615|25
GeForce GTX 760A|25
Toshiba GeForce GT 525M|25
GeForce GT 520MX|25
GeForce GT 620|25
GeForce GT 625|25
GeForce GT 710|24
Quadro NVS 4200M|24
GeForce 840A|24
GeForce 610M|24
GeForce 800M|24
GeForce GT 420|24
GeForce 705M|23
GeForce GT 705|23
GeForce 800M|23
GeForce 610M|23
GeForce GT 620 OEM|23
GeForce GT 625|23
GeForce GT 420|23
Quadro NVS 4200M|23
GeForce GT 520M|22
NVS 4200M|22
GeForce GT 620 OEM|22
NVS 5200M|22
GeForce GT 620 OEM|22
GeForce GT 620|22
GeForce GT 705|21
GeForce GT 620|21
GeForce GT 630 Rev. 2|21
Quadro NVS 4200M|21
GeForce GT 520M|20
GTX 980M SLI|20
GeForce GT 620|20
GeForce GT 520M|20
GeForce GT 520|19
GeForce 410M|19
GeForce 730A|19
GeForce GT 520|19
GeForce GT 610|19
Asus GeForce GT 610|19
NVS 310|18
GeForce 410M|18
NVS 315|18
GeForce 605|18
GeForce GT 610|18
GeForce GT 520|17
GeForce MX550|17
NVS 4200M|17
NVS 315|17
NVS 310|17
GeForce 410M|17
Palit GeForce GTX 660|17
GeForce 605|17
NVS 310|17
GeForce GT 415M|17
Zotac GeForce GT 610|17
GeForce GTX 675M|17
GeForce GT 610|16
Quadro 4000M|16
PNY GeForce GT 610|16
GeForce GT 610|16
GeForce 510|15
MSi GeForce GT 610|15
GeForce GT 735M|15
GeForce GT 520|15
GeForce 510|15
GeForce GT 320M|14
GeForce 9600M GT|14
GeForce GTX 570M|14
Corporation D3D12 (NVIDIA GeForce RTX 3080 Ti)|13
GeForce 510|13
Quadro FX 1800M|12
Asus GeForce GT 520|12
GeForce GT 705|12
MSi GeForce GT 630|11
Quadro 3000M|10
Gigabyte GeForce GT 610|10
Pegatron GeForce GT 420|9
GeForce 210|8
GeForce 9300 / nForce 730i|7
NVS 3100M|7
GeForce 8600 GT|5
GeForce 8400 GS Rev. 3|4
GeForce 8400 GS|3
GeForce 9600 GT|2
GeForce GT 550M|-1
GeForce 8600 GTS|-1
GeForce GT 520MX|-1
EVGA GeForce GTX 460|-1
EVGA GeForce GTX 970|-1
GP106|-1
GRID P4-2B|-1
Gainward GeForce GTX 650|-1
GeForce 210|-1
GeForce 310|-1
GeForce 310M|-1
GeForce 315|-1
GeForce 315M|-1
GeForce 320M|-1
GeForce 405|-1
GeForce 610M|-1
GeForce 820A|-1
GeForce 8300 GS|-1
GeForce 8400 GS|-1
GeForce 8400 GS Rev. 2|-1
GeForce 8400 GS Rev. 3|-1
GeForce 8400M GS|-1
GeForce 8400M GT|-1
GeForce 8500 GT|-1
GeForce 8600 GT|-1
GeForce 8600M GS|-1
GeForce 8600M GT|-1
GeForce 8700M GT|-1
GeForce 8800 GT|-1
GeForce 8800 GTS|-1
GeForce 8800 GTS 512|-1
GeForce 8800 GTX|-1
GeForce 8800M GTX|-1
GeForce 9200M GE|-1
GeForce 9200M GS|-1
GeForce 9300 / nForce 730i|-1
GeForce 9300 GE|-1
GeForce 9300 GS|-1
GeForce 9300M GS|-1
GeForce 9400|-1
GeForce 9400M|-1
GeForce 9500 GT|-1
GeForce 9500M GS|-1
GeForce 9600 GS|-1
GeForce 9600 GSO|-1
GeForce 9600 GSO 512|-1
GeForce 9600 GT|-1
GeForce 9600M GS|-1
GeForce 9600M GT|-1
GeForce 9600M GT / GeForce GT 220M|-1
GeForce 9800 GT|-1
GeForce 9800 GTX+|-1
GeForce 9800 GTX/9800 GTX+|-1
GeForce 9800M GTS|-1
GeForce G 103M|-1
GeForce G 105M|-1
GeForce G105M|-1
GeForce G205M|-1
GeForce G210|-1
GeForce G210M|-1
GeForce GT 120|-1
GeForce GT 120M|-1
GeForce GT 130|-1
GeForce GT 130M|-1
GeForce GT 220|-1
GeForce GT 220M|-1
GeForce GT 230|-1
GeForce GT 230M|-1
GeForce GT 240|-1
GeForce GT 240M|-1
GeForce GT 240M|-1
GeForce GT 320|-1
GeForce GT 320M|-1
GeForce GT 325M|-1
GeForce GT 330|-1
GeForce GT 330M|-1
GeForce GT 335M|-1
GeForce GT 435M|-1
GeForce GT 520M|-1
GeForce GT 525M|-1
GeForce GT 555M/635M|-1
GeForce GTS 240|-1
GeForce GTS 250|-1
GeForce GTS 360M|-1
GeForce GTX 1180|-1
GeForce GTX 260|-1
GeForce GTX 260M|-1
GeForce GTX 275|-1
GeForce GTX 280|-1
GeForce GTX 285|-1
GeForce GTX 295|-1
GeForce GTX 560 SE|-1
GeForce GTX 750 v2|-1
GeForce RTX T10-16|-1
GeForce RTX T10-8|-1
Gigabyte GeForce GTX 1050 Ti|-1
ION|-1
MSI GeForce GT 710|-1
NVS 300|-1
NVS 3100M|-1
NVS 4200M|-1
NVS 5100M|-1
Palit GTX 680 JetStream|-1
Quadro FX 1700|-1
Quadro FX 1700M|-1
Quadro FX 1800|-1
Quadro FX 1800M|-1
Quadro FX 2700M|-1
Quadro FX 2800M|-1
Quadro FX 3600M|-1
Quadro FX 360M|-1
Quadro FX 370|-1
Quadro FX 3700|-1
Quadro FX 3700M|-1
Quadro FX 380 LP|-1
Quadro FX 3800|-1
Quadro FX 3800M|-1
Quadro FX 4600|-1
Quadro FX 4800|-1
Quadro FX 4800|-1
Quadro FX 5600|-1
Quadro FX 570M|-1
Quadro FX 580|-1
Quadro FX 770M|-1
Quadro FX 880M|-1
Quadro K1100M by Nick[D]vB|-1
Quadro K2000D|-1
Quadro K2000M|-1
Quadro K2100M by Nick[D]vB|-1
Quadro NVS 135M|-1
Quadro NVS 140M|-1
Quadro NVS 160M|-1
Quadro NVS 290|-1
Quadro NVS 295|-1
Quadro NVS 4200M|-1
Quadro P4000 OpenGL Engine|-1
Sony GeForce 410M|-1
Zotac GeForce GTX 780|-1
`;function n(){return o}},121559:function(e,t,r){"use strict";r.d(t,{n:function(){return i}});var o=r(347779),n=r(336857);function i(e,t){var r;return n.Z?e?r=(0,o.mf)(e)?e():"current"in e?e.current:e:t:void 0}},559667:function(e,t,r){"use strict";var o=r(716997).default;Object.defineProperty(t,"__esModule",{value:!0}),t.default=function(e){(0,i.default)(1,arguments);var t=(0,n.default)(e),r=t.getUTCFullYear(),o=new Date(0);o.setUTCFullYear(r+1,0,4),o.setUTCHours(0,0,0,0);var c=(0,a.default)(o),s=new Date(0);s.setUTCFullYear(r,0,4),s.setUTCHours(0,0,0,0);var G=(0,a.default)(s);return t.getTime()>=c.getTime()?r+1:t.getTime()>=G.getTime()?r:r-1};var n=o(r(698406)),i=o(r(417816)),a=o(r(943942));e.exports=t.default},199351:function(e,t,r){"use strict";var o=r(68591),n=r(951640),i=r(951530),a=r(715719),c=r(74301),s={code:"en-US",formatDistance:o.Z,formatLong:n.Z,formatRelative:i.Z,localize:a.Z,match:c.Z,options:{weekStartsOn:0,firstWeekContainsDate:1}};t.Z=s},577175:function(e,t,r){var o=r(184539);e.exports=function(e){return o(e,5)}},991876:function(e){var t=Array.isArray;e.exports=t},628680:function(e,t,r){"use strict";e.exports=n;var o=r(440930);function n(e,t){this.lo=e>>>0,this.hi=t>>>0}var i=n.zero=new n(0,0);i.toNumber=function(){return 0},i.zzEncode=i.zzDecode=function(){return this},i.length=function(){return 1};var a=n.zeroHash="\0\0\0\0\0\0\0\0";n.fromNumber=function(e){if(0===e)return i;var t=e<0;t&&(e=-e);var r=e>>>0,o=(e-r)/4294967296>>>0;return t&&(o=~o>>>0,r=~r>>>0,++r>4294967295&&(r=0,++o>4294967295&&(o=0))),new n(r,o)},n.from=function(e){if("number"==typeof e)return n.fromNumber(e);if(o.isString(e)){if(!o.Long)return n.fromNumber(parseInt(e,10));e=o.Long.fromString(e)}return e.low||e.high?new n(e.low>>>0,e.high>>>0):i},n.prototype.toNumber=function(e){if(!e&&this.hi>>>31){var t=~this.lo+1>>>0,r=~this.hi>>>0;return!t&&(r=r+1>>>0),-(t+4294967296*r)}return this.lo+4294967296*this.hi},n.prototype.toLong=function(e){return o.Long?new o.Long(0|this.lo,0|this.hi,!!e):{low:0|this.lo,high:0|this.hi,unsigned:!!e}};var c=String.prototype.charCodeAt;n.fromHash=function(e){return e===a?i:new n((c.call(e,0)|c.call(e,1)<<8|c.call(e,2)<<16|c.call(e,3)<<24)>>>0,(c.call(e,4)|c.call(e,5)<<8|c.call(e,6)<<16|c.call(e,7)<<24)>>>0)},n.prototype.toHash=function(){return String.fromCharCode(255&this.lo,this.lo>>>8&255,this.lo>>>16&255,this.lo>>>24,255&this.hi,this.hi>>>8&255,this.hi>>>16&255,this.hi>>>24)},n.prototype.zzEncode=function(){var e=this.hi>>31;return this.hi=((this.hi<<1|this.lo>>>31)^e)>>>0,this.lo=(this.lo<<1^e)>>>0,this},n.prototype.zzDecode=function(){var e=-(1&this.lo);return this.lo=((this.lo>>>1|this.hi<<31)^e)>>>0,this.hi=(this.hi>>>1^e)>>>0,this},n.prototype.length=function(){var e=this.lo,t=(this.lo>>>28|this.hi<<4)>>>0,r=this.hi>>>24;return 0===r?0===t?e<16384?e<128?1:2:e<2097152?3:4:t<16384?t<128?5:6:t<2097152?7:8:r<128?9:10}},998470:function(e,t,r){"use strict";r.r(t)},938720:function(e,t,r){"use strict";r.r(t)},431187:function(e,t,r){"use strict";r.d(t,{g:function(){return d}}),r(370483),r(847119);var o=r(703196),n=r(256195),i=r.n(n),a=r(861275),c=r.n(a),s=r(709199);r(860276);var G=r(879338),l=function(e,t){var r={};for(var o in e)Object.prototype.hasOwnProperty.call(e,o)&&0>t.indexOf(o)&&(r[o]=e[o]);if(null!=e&&"function"==typeof Object.getOwnPropertySymbols)for(var n=0,o=Object.getOwnPropertySymbols(e);n<o.length;n++)0>t.indexOf(o[n])&&Object.prototype.propertyIsEnumerable.call(e,o[n])&&(r[o[n]]=e[o[n]]);return r};let u=["xxl","xl","lg","md","sm","xs"],d=o.createContext(null),T={xs:"(max-width: 575px)",sm:"(min-width: 576px)",md:"(min-width: 768px)",lg:"(min-width: 992px)",xl:"(min-width: 1200px)",xxl:"(min-width: 1600px)"};class p extends o.Component{componentDidMount(){this.unRegisters=Object.keys(T).map(e=>(0,G.ql)(T[e],{match:()=>{if("object"==typeof this.props.gutter)this.setState(t=>({screens:Object.assign(Object.assign({},t.screens),{[e]:!0})}))},unmatch:()=>{if("object"==typeof this.props.gutter)this.setState(t=>({screens:Object.assign(Object.assign({},t.screens),{[e]:!1})}))}}))}componentWillUnmount(){this.unRegisters.forEach(e=>e())}getGutter(){let{gutter:e=0}=this.props,t=[0,0];return(Array.isArray(e)?e.slice(0,2):[e,0]).forEach((e,r)=>{if("object"==typeof e)for(let o=0;o<u.length;o++){let n=u[o];if(this.state.screens[n]&&void 0!==e[n]){t[r]=e[n];break}}else t[r]=e||0}),t}render(){let e=this.props,{prefixCls:t,type:r,justify:n,align:a,className:c,style:s,children:G}=e,u=l(e,["prefixCls","type","justify","align","className","style","children"]),T=this.getGutter(),p=`${t}-row`,h=i()({[p]:"flex"!==r,[`${p}-${r}`]:r,[`${p}-${r}-${n}`]:r&&n,[`${p}-${r}-${a}`]:r&&a},c),F=Object.assign(Object.assign(Object.assign({},T[0]>0?{marginLeft:-(T[0]/2),marginRight:-(T[0]/2)}:{}),T[1]>0?{marginTop:-(T[1]/2),marginBottom:-(T[1]/2)}:{}),s),f=Object.assign({},u);return delete f.gutter,o.createElement(d.Provider,{value:{gutters:T}},o.createElement("div",Object.assign({},f,{className:h,style:F,"x-semi-prop":"children"}),G))}constructor(){super(...arguments),this.state={screens:{xs:!0,sm:!0,md:!0,lg:!0,xl:!0,xxl:!0}},this.unRegisters=[]}}p.propTypes={type:c().oneOf(["flex"]),align:c().oneOf(["top","middle","bottom"]),justify:c().oneOf(["start","end","center","space-around","space-between"]),className:c().string,style:c().object,children:c().node,gutter:c().oneOfType([c().object,c().number,c().array]),prefixCls:c().string},p.defaultProps={prefixCls:s.U.PREFIX},p.RowContext={gutters:c().any},t.Z=p},801794:function(e,t,r){"use strict";r(370483),r(847119);var o=r(703196),n=r(256195),i=r.n(n),a=r(762304),c=r(906943),s=r(271838),G=r(467738);r(562600);var l=function(e,t){var r={};for(var o in e)Object.prototype.hasOwnProperty.call(e,o)&&0>t.indexOf(o)&&(r[o]=e[o]);if(null!=e&&"function"==typeof Object.getOwnPropertySymbols)for(var n=0,o=Object.getOwnPropertySymbols(e);n<o.length;n++)0>t.indexOf(o[n])&&Object.prototype.propertyIsEnumerable.call(e,o[n])&&(r[o[n]]=e[o[n]]);return r};let u=c.U.PREFIX;class d extends s.Z{componentDidMount(){this.foundation.init(),window.addEventListener("resize",this.foundation.ensureConstraint)}componentDidUpdate(e){this.props.direction!==e.direction&&(this.setState(e=>Object.assign(Object.assign({},e),{contextValue:Object.assign(Object.assign({},e.contextValue),{direction:this.props.direction})})),this.foundation.direction=this.props.direction)}componentWillUnmount(){this.foundation.destroy(),window.removeEventListener("resize",this.foundation.ensureConstraint)}get adapter(){return Object.assign(Object.assign({},super.adapter),{getGroupRef:()=>this.groupRef.current,getItem:e=>this.itemRefs.get(e).current,getItemCount:()=>this.itemRefs.size,getHandler:e=>this.handlerRefs.get(e).current,getHandlerCount:()=>this.handlerRefs.size,getItemMin:e=>this.itemMinMap.get(e),getItemMax:e=>this.itemMaxMap.get(e),getItemChange:e=>this.itemResizing.get(e),getItemEnd:e=>this.itemResizeEnd.get(e),getItemStart:e=>this.itemResizeStart.get(e),getItemDefaultSize:e=>this.itemDefaultSizeList.get(e),registerEvents:this.registerEvent,unregisterEvents:this.unregisterEvent})}get window(){var e;return null!==(e=this.groupRef.current.ownerDocument.defaultView)&&void 0!==e?e:null}render(){let e=this.props,{children:t,direction:r,className:n}=e,a=l(e,["children","direction","className"]);return o.createElement(G.M.Provider,{value:this.state.contextValue},o.createElement("div",Object.assign({style:{flexDirection:"vertical"===r?"column":"row"},ref:this.groupRef,className:i()(n,u+"-group")},a),this.state.isResizing&&o.createElement("div",{style:this.state.backgroundStyle,className:i()(n,u+"-background")}),t))}constructor(e){var t;super(e),t=this,this.itemRefs=new Map,this.itemMinMap=new Map,this.itemMaxMap=new Map,this.itemMinusMap=new Map,this.itemDefaultSizeList=new Map,this.itemResizeStart=new Map,this.itemResizing=new Map,this.itemResizeEnd=new Map,this.handlerRefs=new Map,this.registerEvent=function(){let e=arguments.length>0&&void 0!==arguments[0]?arguments[0]:"mouse";t.window&&("mouse"===e?(t.window.addEventListener("mousemove",t.foundation.onMouseMove),t.window.addEventListener("mouseup",t.foundation.onResizeEnd),t.window.addEventListener("mouseleave",t.foundation.onResizeEnd)):(t.window.addEventListener("touchmove",t.foundation.onTouchMove,{passive:!1}),t.window.addEventListener("touchend",t.foundation.onResizeEnd),t.window.addEventListener("touchcancel",t.foundation.onResizeEnd)))},this.unregisterEvent=function(){let e=arguments.length>0&&void 0!==arguments[0]?arguments[0]:"mouse";t.window&&("mouse"===e?(t.window.removeEventListener("mousemove",t.foundation.onMouseMove),t.window.removeEventListener("mouseup",t.foundation.onResizeEnd),t.window.removeEventListener("mouseleave",t.foundation.onResizeEnd)):(t.window.removeEventListener("touchmove",t.foundation.onTouchMove,{passive:!1}),t.window.removeEventListener("touchend",t.foundation.onResizeEnd),t.window.removeEventListener("touchcancel",t.foundation.onResizeEnd)))},this.registerItem=(e,t,r,o,n,i,a)=>{if(Array.from(this.itemRefs.values()).some(t=>t===e))return -1;let c=this.itemRefs.size;return this.itemRefs.set(c,e),this.itemMinMap.set(c,t),this.itemMaxMap.set(c,r),this.itemDefaultSizeList.set(c,o),this.itemResizeStart.set(c,n),this.itemResizing.set(c,i),this.itemResizeEnd.set(c,a),c},this.registerHandler=e=>{if(Array.from(this.handlerRefs.values()).some(t=>t===e))return -1;let t=this.handlerRefs.size;return this.handlerRefs.set(t,e),t},this.getGroupSize=()=>this.groupSize,this.groupRef=(0,o.createRef)(),this.foundation=new a.qY(this.adapter),this.state={isResizing:!1,originalPosition:{x:0,y:0,lastItemSize:0,nextItemSize:0,lastOffset:0,nextOffset:0},backgroundStyle:{cursor:"auto"},curHandler:null,contextValue:{direction:e.direction,registerItem:this.registerItem,registerHandler:this.registerHandler,notifyResizeStart:this.foundation.onResizeStart,getGroupSize:this.getGroupSize}}}}d.propTypes={},d.defaultProps={direction:"horizontal"},d.contextType=G.M,t.Z=d},710979:function(e,t,r){"use strict";r.d(t,{D:function(){return f}}),r(428647),r(847119),r(19526),r(370483);var o=r(18782),n=r.n(o),i=r(977353),a=r.n(i),c=r(703196),s=r(861275),G=r.n(s),l=r(256195),u=r.n(l),d=r(26910),T=r(270840),p=r(145989),h=r(625523),F=function(e,t){var r={};for(var o in e)Object.prototype.hasOwnProperty.call(e,o)&&0>t.indexOf(o)&&(r[o]=e[o]);if(null!=e&&"function"==typeof Object.getOwnPropertySymbols)for(var n=0,o=Object.getOwnPropertySymbols(e);n<o.length;n++)0>t.indexOf(o[n])&&Object.prototype.propertyIsEnumerable.call(e,o[n])&&(r[o[n]]=e[o[n]]);return r};let f={record:G().object,index:G().number,columns:G().array,group:G().object.isRequired,groupKey:G().oneOfType([G().string,G().number]).isRequired,data:G().array,renderGroupSection:G().func,onGroupedRow:G().func,clickGroupedRowToExpand:G().bool,components:G().object,expanded:G().bool,prefixCls:G().string,onExpand:G().func,virtualized:G().oneOfType([G().bool,G().object]),style:G().object,renderExpandIcon:G().func,className:G().string,store:G().object,rowKey:G().oneOfType([G().string,G().number,G().func])};class g extends c.PureComponent{isInnerColumnKey(e){return null!=e&&[d.j2.DEFAULT_KEY_COLUMN_EXPAND,d.j2.DEFAULT_KEY_COLUMN_SELECTION].includes(e)}render(){let{record:e,columns:t=[],prefixCls:r,className:o,expanded:n,renderGroupSection:i,components:a,index:s,store:G,group:l,groupKey:d,virtualized:h,style:f}=this.props,g={},X={},M=null,m="function"==typeof i?i(d,[...l]):null;if((0,c.isValidElement)(m))M=m;else if(m&&"[object Object]"===Object.prototype.toString.call(m)){let{children:e}=m,t=F(m,["children"]);M=e,X=Object.assign({},t)}g.colSpan=(0,T.I2)(t).length;let v=[Object.assign({render:()=>({props:g,children:M})},X)],y=u()(o,`${r}-row-section`,{on:n}),{getCellWidths:b}=this.context,E=b(v,null,!0);return c.createElement(p.Z,{components:a,virtualized:h,index:s,onRow:this.onRow,expanded:n,expandIcon:!0,isSection:!0,record:e,replaceClassName:y,expandableRow:!0,renderExpandIcon:this.renderExpandIcon,rowKey:d,columns:v,store:G,style:f,cellWidths:E})}constructor(){var e;super(...arguments),e=this,this.onRow=function(){let{onGroupedRow:t,clickGroupedRowToExpand:r,onExpand:o,groupKey:n,expanded:i}=e.props,a={};return"function"==typeof t&&Object.assign(a,t(...arguments)),Object.assign(Object.assign({},a),{onClick:e=>{"function"==typeof o&&r&&o(!i,n,e),"function"==typeof a.onClick&&a.onClick(e)}})},this.collectGroupedData=()=>{let{data:e,group:t,rowKey:r}=this.props;return Array.isArray(e)&&e.length&&n()(t)?e.filter(e=>{let o="function"==typeof r?r(e):a()(e,r);return null!=o&&""!==o&&t.has(o)}):[]},this.renderExpandIcon=e=>{let{renderExpandIcon:t,groupKey:r}=this.props;return"function"==typeof t?t(e,!1,r):null}}}g.contextType=h.Z,g.propTypes=f,g.defaultProps={prefixCls:d.UX.PREFIX,components:{body:{row:"tr",cell:"td"}}},t.Z=g},368914:function(e,t,r){"use strict";r.d(t,{Z:function(){return Z}}),r("370483"),r("847119"),r("428647");var o=r("718303"),n=r.n(o),i=r("661654"),a=r.n(i),c=r("875358"),s=r.n(c),G=r("87642"),l=r.n(G),u=r("744495"),d=r.n(u),T=r("977353"),p=r.n(T),h=r("639444"),F=r.n(h),f=r("662315"),g=r.n(f),X=r("703196"),M=r("408812"),m=r("256195"),v=r.n(m),y=r("861275"),b=r.n(y),E=r("776045"),R=r("237073"),S=r("844381"),P=r("685581"),Q=r("57739"),O=r("737044"),w=r("889287");r("958620");var L=r("271838"),A=r("787007"),I=r("879338"),C=r("536336"),x=r("794840"),D=r("178140"),_=function(e,t){var r={};for(var o in e)Object.prototype.hasOwnProperty.call(e,o)&&0>t.indexOf(o)&&(r[o]=e[o]);if(null!=e&&"function"==typeof Object.getOwnPropertySymbols)for(var n=0,o=Object.getOwnPropertySymbols(e);n<o.length;n++)0>t.indexOf(o[n])&&Object.prototype.propertyIsEnumerable.call(e,o[n])&&(r[o[n]]=e[o[n]]);return r},N=e=>{let{className:t,style:r}=e,o=_(e,["className","style"]);return X.createElement("svg",Object.assign({"aria-hidden":!0,className:t,style:r},o,{width:"7",height:"24",xmlns:"http://www.w3.org/2000/svg",fill:"currentColor"}),X.createElement("path",{d:"M0 0L1 0C1 4, 2 5.5, 4 7.5S7,10 7,12S6 14.5, 4 16.5S1,20 1,24L0 24L0 0z"}))},k=r("338618"),K=r("986618"),j=function(e,t){var r={};for(var o in e)Object.prototype.hasOwnProperty.call(e,o)&&0>t.indexOf(o)&&(r[o]=e[o]);if(null!=e&&"function"==typeof Object.getOwnPropertySymbols)for(var n=0,o=Object.getOwnPropertySymbols(e);n<o.length;n++)0>t.indexOf(o[n])&&Object.prototype.propertyIsEnumerable.call(e,o[n])&&(r[o[n]]=e[o[n]]);return r};let U=O.UX.PREFIX,V=O.j2.POSITION_SET,B=O.j2.TRIGGER_SET,z=["flex","block","table","flow-root","grid"],H=()=>document.body;class Z extends L.Z{get adapter(){var e=this;return Object.assign(Object.assign({},super.adapter),{on:function(){return e.eventManager.on(...arguments)},off:function(){return e.eventManager.off(...arguments)},getAnimatingState:()=>this.isAnimating,insertPortal:(e,t)=>{var{position:r}=t,o=j(t,["position"]);this.setState({isInsert:!0,transitionState:"enter",containerStyle:Object.assign(Object.assign({},this.state.containerStyle),o)},()=>{setTimeout(()=>{this.setState(e=>("enter"===e.transitionState&&this.eventManager.emit("portalInserted"),{}))},0)})},removePortal:()=>{this.setState({isInsert:!1,isPositionUpdated:!1})},getEventName:()=>({mouseEnter:"onMouseEnter",mouseLeave:"onMouseLeave",mouseOut:"onMouseOut",mouseOver:"onMouseOver",click:"onClick",focus:"onFocus",blur:"onBlur",keydown:"onKeyDown",contextMenu:"onContextMenu"}),registerTriggerEvent:e=>{this.setState({triggerEventSet:e})},registerPortalEvent:e=>{this.setState({portalEventSet:e})},getTriggerBounding:()=>{let e=this.adapter.getTriggerNode();return this.triggerEl.current=e,e&&e.getBoundingClientRect()},getPopupContainerRect:()=>{let e=this.getPopupContainer(),t=null;return e&&(0,A.Z)(e)&&(t=Object.assign(Object.assign({},(0,P.I3)(e.getBoundingClientRect())),{scrollLeft:e.scrollLeft,scrollTop:e.scrollTop})),t},containerIsBody:()=>this.getPopupContainer()===document.body,containerIsRelative:()=>{let e=this.getPopupContainer();return"relative"===window.getComputedStyle(e).getPropertyValue("position")},containerIsRelativeOrAbsolute:()=>["relative","absolute"].includes(this.containerPosition),getWrapperBounding:()=>{let e=this.containerEl&&this.containerEl.current;return e&&e.getBoundingClientRect()},getDocumentElementBounding:()=>document.documentElement.getBoundingClientRect(),setPosition:e=>{var{position:t}=e,r=j(e,["position"]);this.setState({containerStyle:Object.assign(Object.assign({},this.state.containerStyle),r),placement:t,isPositionUpdated:!0},()=>{this.eventManager.emit("positionUpdated")})},setDisplayNone:(e,t)=>{this.setState({displayNone:e},t)},updatePlacementAttr:e=>{this.setState({placement:e})},togglePortalVisible:(e,t)=>{let r={};r.transitionState=e?"enter":"leave",r.visible=e,this.mounted&&this.setState(r,()=>{t()})},registerClickOutsideHandler:e=>{this.clickOutsideHandler&&this.adapter.unregisterClickOutsideHandler(),this.clickOutsideHandler=t=>{if(!this.mounted)return!1;let r=this.triggerEl&&this.triggerEl.current,o=this.containerEl&&this.containerEl.current;r=M.findDOMNode(r),o=M.findDOMNode(o);let n=t.target,i=t.composedPath&&t.composedPath()||[n],a=!!this.props.clickTriggerToHide&&(r&&r.contains(n)||i.includes(r));(r&&!r.contains(n)&&o&&!o.contains(n)&&!(i.includes(o)||i.includes(r))||a)&&(this.props.onClickOutSide(t),e())},window.addEventListener("mousedown",this.clickOutsideHandler)},unregisterClickOutsideHandler:()=>{this.clickOutsideHandler&&(window.removeEventListener("mousedown",this.clickOutsideHandler),this.clickOutsideHandler=null)},registerResizeHandler:e=>{this.resizeHandler&&this.adapter.unregisterResizeHandler(),this.resizeHandler=g()(t=>{if(!this.mounted)return!1;e(t)},10),window.addEventListener("resize",this.resizeHandler,!1)},unregisterResizeHandler:()=>{this.resizeHandler&&(window.removeEventListener("resize",this.resizeHandler,!1),this.resizeHandler=null)},notifyVisibleChange:e=>{this.props.onVisibleChange(e)},registerScrollHandler:e=>{this.scrollHandler&&this.adapter.unregisterScrollHandler(),this.scrollHandler=g()(t=>{if(!this.mounted)return!1;let r=this.adapter.getTriggerNode();t.target.contains(r)&&e({x:t.target.scrollLeft,y:t.target.scrollTop})},10),window.addEventListener("scroll",this.scrollHandler,!0)},unregisterScrollHandler:()=>{this.scrollHandler&&(window.removeEventListener("scroll",this.scrollHandler,!0),this.scrollHandler=null)},canMotion:()=>!!this.props.motion,updateContainerPosition:()=>{let e=this.getPopupContainer();if(e&&(0,A.Z)(e)){let t=window.getComputedStyle(e).getPropertyValue("position");this.containerPosition=t}},getContainerPosition:()=>this.containerPosition,getContainer:()=>this.containerEl&&this.containerEl.current,getTriggerNode:()=>{let e=this.triggerEl.current;return!(0,A.Z)(this.triggerEl.current)&&(e=M.findDOMNode(this.triggerEl.current)),e},getFocusableElements:e=>(0,I.GO)(e),getActiveElement:()=>(0,I.vY)(),setInitialFocus:()=>{let{preventScroll:e}=this.props,t=p()(this,"initialFocusRef.current");t&&"focus"in t&&t.focus({preventScroll:e})},notifyEscKeydown:e=>{this.props.onEscKeyDown(e)},setId:()=>{this.setState({id:(0,w.Ms)()})},getTriggerDOM:()=>this.triggerEl.current?M.findDOMNode(this.triggerEl.current):null})}componentDidMount(){this.mounted=!0,this.getPopupContainer=this.props.getPopupContainer||this.context.getPopupContainer||H,this.foundation.init(),(0,I.Tq)(()=>{let e=this.triggerEl.current;e&&!(e instanceof HTMLElement)&&(e=(0,M.findDOMNode)(e)),this.foundation.updateStateIfCursorOnTrigger(e)},1)}componentWillUnmount(){this.mounted=!1,this.foundation.destroy()}focusTrigger(){this.foundation.focusTrigger()}rePosition(){return this.foundation.calcPosition()}componentDidUpdate(e,t){(0,R.Z)(this.props.mouseLeaveDelay<this.props.mouseEnterDelay,"[Semi Tooltip] 'mouseLeaveDelay' cannot be less than 'mouseEnterDelay', which may cause the dropdown layer to not be hidden."),e.visible!==this.props.visible&&(["hover","focus"].includes(this.props.trigger)?this.props.visible?this.foundation.delayShow():this.foundation.delayHide():this.props.visible?this.foundation.show():this.foundation.hide()),!n()(e.rePosKey,this.props.rePosKey)&&this.rePosition()}render(){let{isInsert:e,triggerEventSet:t,visible:r,id:o}=this.state,{wrapWhenSpecial:n,role:i,trigger:a}=this.props,{children:c}=this.props,s=Object.assign({},p()(c,"props.style")),G={};if(n){let e=this.isSpecial(c);e?(s.pointerEvents="none",e===O.j2.STATUS_DISABLED&&(G.cursor="not-allowed"),c=(0,X.cloneElement)(c,{style:s}),"custom"!==a&&(c=this.wrapSpan(c)),this.isWrapped=!0):!(0,X.isValidElement)(c)&&(c=this.wrapSpan(c),this.isWrapped=!0)}let l={};"dialog"===i?(l["aria-expanded"]=r?"true":"false",l["aria-haspopup"]="dialog",l["aria-controls"]=o):l["aria-describedby"]=o;let u=X.cloneElement(c,Object.assign(Object.assign(Object.assign(Object.assign({},l),c.props),this.mergeEvents(c.props,t)),{style:Object.assign(Object.assign({},p()(c,"props.style")),G),className:v()(p()(c,"props.className")),ref:e=>{this.triggerEl.current=e;let{ref:t}=c;"function"==typeof t?t(e):t&&"object"==typeof t&&(t.current=e)},tabIndex:c.props.tabIndex||0,"data-popupid":o}));return X.createElement(X.Fragment,null,e?this.renderPortal():null,u)}constructor(e){super(e),this.isAnimating=!1,this.setContainerEl=e=>this.containerEl={current:e},this.isSpecial=e=>{if((0,A.Z)(e))return!!e.disabled;if((0,X.isValidElement)(e)){if(p()(e,"props.disabled"))return O.j2.STATUS_DISABLED;let t=p()(e,"props.loading"),r=!s()(e)&&!s()(e.type)&&("Button"===p()(e,"type.elementType")||"IconButton"===p()(e,"type.elementType"));if(t&&r)return O.j2.STATUS_LOADING}return!1},this.didLeave=()=>{this.props.keepDOM?this.foundation.setDisplayNone(!0):this.foundation.removePortal(),this.foundation.unBindEvent()},this.renderIcon=()=>{let{placement:e}=this.state,{showArrow:t,prefixCls:r,style:o}=this.props,n=null,i=v()([`${r}-icon-arrow`]),a=p()(o,"backgroundColor"),c=(null==e?void 0:e.includes("left"))||(null==e?void 0:e.includes("right"))?X.createElement(N,null):X.createElement(D.Z,null);return t&&(n=(0,X.isValidElement)(t)?t:X.cloneElement(c,{className:i,style:{color:a,fill:"currentColor"}})),n},this.handlePortalInnerClick=e=>{this.props.clickToHide&&this.foundation.hide(),this.props.stopPropagation&&(0,I.UW)(e)},this.handlePortalMouseDown=e=>{this.props.stopPropagation&&(0,I.UW)(e)},this.handlePortalFocus=e=>{this.props.stopPropagation&&(0,I.UW)(e)},this.handlePortalBlur=e=>{this.props.stopPropagation&&(0,I.UW)(e)},this.handlePortalInnerKeyDown=e=>{this.foundation.handleContainerKeydown(e)},this.renderContentNode=e=>{let t={initialFocusRef:this.initialFocusRef};return a()(e)?e(t):e},this.renderPortal=()=>{let{containerStyle:e={},visible:t,portalEventSet:r,placement:o,displayNone:n,transitionState:i,id:a,isPositionUpdated:c}=this.state,{prefixCls:s,content:G,showArrow:l,style:u,motion:T,role:h,zIndex:F}=this.props,f=this.renderContentNode(G),{className:g}=this.props,M=this.context.direction,m=v()(g,{[`${s}-wrapper`]:!0,[`${s}-wrapper-show`]:t,[`${s}-with-arrow`]:!!l,[`${s}-rtl`]:"rtl"===M}),y=this.renderIcon(),b=d()(e,T?["transformOrigin"]:void 0),R=p()(e,"transformOrigin"),S=p()(u,"opacity",null),P=S||1,Q=X.createElement(K.Z,{fillMode:"forwards",animationState:i,motion:T&&c,startClassName:"enter"===i?`${U}-animation-show`:`${U}-animation-hide`,onAnimationStart:()=>this.isAnimating=!0,onAnimationEnd:()=>{var e,t;"leave"===i&&(this.didLeave(),null===(t=(e=this.props).afterClose)||void 0===t||t.call(e)),this.isAnimating=!1}},e=>{let{animationStyle:t,animationClassName:i,animationEventsNeedBind:s}=e;return X.createElement("div",Object.assign({className:v()(m,i),style:Object.assign(Object.assign(Object.assign(Object.assign(Object.assign({},t),n?{display:"none"}:{}),{transformOrigin:R}),u),S?{opacity:c?P:"0"}:{})},r,s,{role:h,"x-placement":o,id:a}),X.createElement("div",{className:`${U}-content`},f),y)});return X.createElement(C.Z,{getPopupContainer:this.props.getPopupContainer,style:{zIndex:F}},X.createElement("div",{tabIndex:-1,className:`${E.T}-portal-inner`,style:b,ref:this.setContainerEl,onClick:this.handlePortalInnerClick,onFocus:this.handlePortalFocus,onBlur:this.handlePortalBlur,onMouseDown:this.handlePortalMouseDown,onKeyDown:this.handlePortalInnerKeyDown},Q))},this.wrapSpan=e=>{let{wrapperClassName:t}=this.props,r=p()(e,"props.style.display"),o=p()(e,"props.block"),n={};return"string"!=typeof e&&(n.display="inline-block"),(o||z.includes(r))&&(n.width="100%"),X.createElement("span",{className:t,style:n},e)},this.mergeEvents=(e,t)=>{let r={};return l()(t,(t,o)=>{"function"==typeof t&&(r[o]=function(){t(...arguments),e&&"function"==typeof e[o]&&e[o](...arguments)})}),r},this.getPopupId=()=>this.state.id,this.state={visible:!1,transitionState:"",triggerEventSet:{},portalEventSet:{},containerStyle:{},isInsert:!1,placement:e.position||"top",transitionStyle:{},isPositionUpdated:!1,id:e.wrapperId,displayNone:!1},this.foundation=new Q.Z(this.adapter),this.eventManager=new S.Z,this.triggerEl=X.createRef(),this.containerEl=X.createRef(),this.initialFocusRef=X.createRef(),this.clickOutsideHandler=null,this.resizeHandler=null,this.isWrapped=!1,this.containerPosition=void 0}}Z.contextType=x.Z,Z.propTypes={children:b().node,motion:b().bool,autoAdjustOverflow:b().bool,position:b().oneOf(V),getPopupContainer:b().func,mouseEnterDelay:b().number,mouseLeaveDelay:b().number,trigger:b().oneOf(B).isRequired,className:b().string,wrapperClassName:b().string,clickToHide:b().bool,clickTriggerToHide:b().bool,visible:b().bool,style:b().object,content:b().oneOfType([b().node,b().func]),prefixCls:b().string,onVisibleChange:b().func,onClickOutSide:b().func,spacing:b().oneOfType([b().number,b().object]),margin:b().oneOfType([b().number,b().object]),showArrow:b().oneOfType([b().bool,b().node]),zIndex:b().number,rePosKey:b().oneOfType([b().string,b().number]),arrowBounding:k.Z,transformFromCenter:b().bool,arrowPointAtCenter:b().bool,stopPropagation:b().bool,role:b().string,wrapWhenSpecial:b().bool,guardFocus:b().bool,returnFocusOnClose:b().bool,preventScroll:b().bool,keepDOM:b().bool},Z.__SemiComponentName__="Tooltip",Z.defaultProps=(0,I.GW)(Z.__SemiComponentName__,{arrowBounding:O.KT.ARROW_BOUNDING,autoAdjustOverflow:!0,arrowPointAtCenter:!0,trigger:"hover",transformFromCenter:!0,position:"top",prefixCls:U,role:"tooltip",mouseEnterDelay:O.KT.MOUSE_ENTER_DELAY,mouseLeaveDelay:O.KT.MOUSE_LEAVE_DELAY,motion:!0,onVisibleChange:F(),onClickOutSide:F(),spacing:O.KT.SPACING,margin:O.KT.MARGIN,showArrow:!0,wrapWhenSpecial:!0,zIndex:O.KT.DEFAULT_Z_INDEX,closeOnEsc:!1,guardFocus:!1,returnFocusOnClose:!1,onEscKeyDown:F(),disableFocusListener:!1,disableArrowKeyDown:!1,keepDOM:!1})},107278:function(e,t,r){"use strict";r.d(t,{j:function(){return o}});let o={STREAM_PARSED:"streamparsed",NO_AUDIO_TRACK:"noaudiotrack",SUBTITLE_SEGMENTS:"subtitlesegments",SUBTITLE_PLAYLIST:"subtitleplaylist",SEI_PAYLOAD_TIME:"seipayloadtime",APPEND_COST:"appendcost"}},6079:function(e,t,r){"use strict";r.d(t,{K:function(){return a}});var o=r(203687),n=r(258343);r(46163),r(207418),r(19526),r(870128),r(370483),r(596629),r(554178),r(847119),r(924006);class i{_normalizeStreamId(e){return e.split("?")[0]}static getInstance(){return!i.instance&&(i.instance=new i),i.instance}static _checkEnablePerformanceAPI(){try{let e=localStorage.getItem("playerlog"),t=Number(e);!Number.isNaN(t)&&t>=2&&(i.enablePerformanceAPI=!0)}catch(e){}}startSession(e){let t=this._normalizeStreamId(e),r=`${t}_${Date.now()}_${Math.random().toString(36).substr(2,9)}`;return this.sessions.get(t),this.sessions.set(t,{streamId:t,startTime:performance.now(),instanceId:r,marks:{},httpRequestCount:0,httpRequests:[],currentHttpStartTime:null}),r}endSession(e,t){let r=this._normalizeStreamId(e),o=this.sessions.get(r);if(!!o&&(!t||o.instanceId===t))this.sessions.delete(r)}mark(e,t){let r=this._normalizeStreamId(e),o=this.sessions.get(r);if(!o)return;let n=performance.now()-o.startTime;if("httpStart"===t)o.httpRequestCount++,o.currentHttpStartTime=n,o.httpRequests.push({index:o.httpRequestCount,startTime:n,endTime:null,duration:null});else if("httpEnd"===t&&null!=o.currentHttpStartTime){let e=o.httpRequests[o.httpRequests.length-1];e&&(e.endTime=n,e.duration=n-e.startTime),o.currentHttpStartTime=null}if("httpEnd"===t){if(o.marks[t]=n,i.enablePerformanceAPI)try{let e=`RTM_${t}`;performance.mark(e)}catch(e){}}else if(null==o.marks[t]&&(o.marks[t]=n,i.enablePerformanceAPI))try{let e=`RTM_${t}`;performance.mark(e)}catch(e){}}markFirstFrame(e){this.mark(e,"firstFrame");let t=this.buildReport(e);return(this.printReport(e),t)?(this._createPerformanceMeasures(t),t):null}setRTCStats(e,t){let r=this._normalizeStreamId(e),o=this.sessions.get(r);o&&Object.assign(o,t)}bindPeerConnection(e,t){let r=this._normalizeStreamId(e);t.oniceconnectionstatechange=()=>{let e=t.iceConnectionState;"checking"===e&&this.mark(r,"iceChecking"),"connected"===e&&this.mark(r,"iceConnected"),"completed"===e&&this.mark(r,"iceCompleted"),"failed"===e&&this.mark(r,"iceFailed")},t.onconnectionstatechange=async()=>{"connected"===t.connectionState&&(this.mark(r,"dtlsConnected"),await this._collectPCStatsWithRetry(r,t))}}getMarkTime(e,t){let r=this._normalizeStreamId(e),o=this.sessions.get(r);return o&&o.marks[t]||null}buildReport(e){let t=this._normalizeStreamId(e),r=this.sessions.get(t);if(!r)return null;let o=r.marks,i=(e,t)=>null!=o[e]&&null!=o[t]?o[t]-o[e]:null,a=e=>null==e?null:Math.max(0,e),c=function(){for(var e=arguments.length,t=Array(e),r=0;r<e;r++)t[r]=arguments[r];return t.some(e=>null==e)?null:t.reduce((e,t)=>e+(t||0),0)},s=a(i("playStart","firstFrame")),G=a(i("playStart","setRemoteStart")),l=null!=G&&null!=o.playStart&&null!=o.setRemoteStart?r.httpRequests.reduce((e,t)=>{if(null==t.endTime)return e;let r=Math.max(t.startTime,o.playStart),n=Math.min(t.endTime,o.setRemoteStart);return n>r?e+(n-r):e},0):null,u=null!=G?Math.max(0,G-(l||0)):null,d=a(i("setRemoteStart","setRemoteEnd")),T=a(i("setRemoteEnd","iceChecking")),p=a(i("iceChecking","iceConnected")),h=a(i("iceConnected","dtlsConnected")),F=a(i("dtlsConnected","firstFrame")),f=c(l,u,d,T,p,h),g=c(f,F),X=null!=s&&null!=g?Math.max(0,s-g):null;return{streamId:r.streamId,startAt:r.startTime,playPhases:{playToFirstFrame:s,preloadPlayOverlap:G,httpSignaling:l,waitPreload:u,setRemote:d,waitIceChecking:T,playToIce:a(i("playStart","iceConnected")),playToDtls:a(i("playStart","dtlsConnected")),iceNegotiation:p,dtlsHandshake:h,waitingFirstFrame:F,additiveKnownPhases:f,additiveResidual:X},preloadPhases:{createOffer:i("createOfferStart","createOfferEnd"),setLocalDescription:i("setLocalStart","setLocalEnd"),httpSignaling:i("httpStart","httpEnd"),httpSignalingTotal:r.httpRequests.reduce((e,t)=>e+(t.duration||0),0)||null,setRemoteDescription:i("setRemoteStart","setRemoteEnd"),httpRequestCount:r.httpRequestCount,httpRequests:r.httpRequests},totalPhases:{total:i("createOfferStart","firstFrame"),dtlsTotal:i("httpEnd","dtlsConnected")},marks:(0,n._)({},o),rtt:r.rtt,localCandidateType:r.localCandidateType,remoteCandidateType:r.remoteCandidateType}}printReport(e){let t=this.buildReport(e);if(!t)return;let r=e=>null!=e?`${e.toFixed(1)}ms`:"N/A";if(t.playPhases,t.preloadPhases.httpSignaling,t.preloadPhases.httpRequestCount>1&&t.preloadPhases.httpRequestCount,this._printTimeline(t),null!=t.marks.createOfferStart&&t.preloadPhases.httpRequestCount>1){let e={"① createOffer":r(t.preloadPhases.createOffer),"② setLocalDescription":r(t.preloadPhases.setLocalDescription)};t.preloadPhases.httpRequests.forEach((t,r)=>{let o=null!=t.duration?"success":"pending";e[`③ HTTP请求#${t.index} (${0===r?"44100Hz":"48000Hz"})`]=null!=t.duration?`${t.duration.toFixed(1)}ms`:o}),e["③ HTTP请求累计耗时"]=r(t.preloadPhases.httpSignalingTotal),e["③ HTTP请求完整耗时(含间隔)"]=r(t.preloadPhases.httpSignaling),e["④ setRemoteDescription"]=r(t.preloadPhases.setRemoteDescription),e["⏱️  预加载总耗时"]=r(t.totalPhases.total)}let o={};Object.entries(t.marks).forEach(e=>{let[t,r]=e;null!=r&&(o[t]=`${r.toFixed(1)}ms`)})}_printTimeline(e){let t=e.playPhases;if(null==t.playToFirstFrame)return;let r=t.playToFirstFrame}_createPerformanceMeasures(e){if(!!i.enablePerformanceAPI)try{let t=e.playPhases;null!=t.playToFirstFrame&&performance.measure("RTM_播放到首帧","RTM_playStart","RTM_firstFrame"),null!=t.setRemote&&performance.measure("RTM_setRemote","RTM_setRemoteStart","RTM_setRemoteEnd"),null!=t.waitIceChecking&&performance.measure("RTM_等待ICE检查","RTM_setRemoteEnd","RTM_iceChecking"),null!=t.iceNegotiation&&performance.measure("RTM_ICE协商","RTM_iceChecking","RTM_iceConnected"),null!=t.dtlsHandshake&&performance.measure("RTM_DTLS握手","RTM_iceConnected","RTM_dtlsConnected"),null!=t.waitingFirstFrame&&performance.measure("RTM_等待首帧数据","RTM_dtlsConnected","RTM_firstFrame"),null!=e.preloadPhases.createOffer&&performance.measure("RTM_createOffer","RTM_createOfferStart","RTM_createOfferEnd"),null!=e.preloadPhases.httpSignaling&&performance.measure("RTM_HTTP信令","RTM_httpStart","RTM_httpEnd")}catch(e){}}async _collectPCStatsWithRetry(e,t){let r=arguments.length>2&&void 0!==arguments[2]?arguments[2]:1,o=1===r?0:200;o>0&&await new Promise(e=>setTimeout(e,o));let n=this._normalizeStreamId(e);!await this._collectPCStats(n,t)&&r<3&&await this._collectPCStatsWithRetry(e,t,r+1)}async _collectPCStats(e,t){try{let n,i,a;let c=await t.getStats(),s=new Map;c.forEach(e=>{("local-candidate"===e.type||"remote-candidate"===e.type)&&s.set(e.id,e)});let G=null;if(c.forEach(e=>{if("candidate-pair"===e.type){let t=!0===e.nominated,r="succeeded"===e.state,o="in-progress"===e.state;if((t||!G&&r||!G&&o)&&(G=e,t))return}}),!G)return!1;{var r,o;n=null!=G.currentRoundTripTime?1e3*G.currentRoundTripTime:void 0,i=null===(r=s.get(G.localCandidateId))||void 0===r?void 0:r.candidateType,a=null===(o=s.get(G.remoteCandidateId))||void 0===o?void 0:o.candidateType,this.setRTCStats(e,{rtt:n,localCandidateType:i,remoteCandidateType:a});let t=null!=n,c=null!=i&&null!=a;return t&&c}}catch(e){return!1}}constructor(){(0,o._)(this,"sessions",new Map),i._checkEnablePerformanceAPI()}}(0,o._)(i,"instance",void 0),(0,o._)(i,"enablePerformanceAPI",!1);let a=i.getInstance()},492078:function(e,t,r){"use strict";r.d(t,{Bc:function(){return s.Bc},FO:function(){return c.FO},WP:function(){return n.W},Xw:function(){return a.X},_$:function(){return c._$},_A:function(){return i._},_e:function(){return s._e},m$:function(){return c.m$},qT:function(){return o.q},yQ:function(){return s.yQ}});var o=r(594117),n=r(265697),i=r(371092),a=r(972971),c=r(874522),s=r(406569)},498510:function(e,t,r){"use strict";r.d(t,{K:function(){return o}}),r(870128);class o{static decode(e){let t=[],r=0,n=e.length;for(;r<n;){if(e[r]<128){t.push(String.fromCharCode(e[r])),++r;continue}if(e[r]<192);else if(e[r]<224){if(o._checkContinuation(e,r,1)){let o=(31&e[r])<<6|63&e[r+1];if(o>=128){t.push(String.fromCharCode(65535&o)),r+=2;continue}}}else if(e[r]<240){if(o._checkContinuation(e,r,2)){let o=(15&e[r])<<12|(63&e[r+1])<<6|63&e[r+2];if(o>=2048&&(63488&o)!=55296){t.push(String.fromCharCode(65535&o)),r+=3;continue}}}else if(e[r]<248&&o._checkContinuation(e,r,3)){let o=(7&e[r])<<18|(63&e[r+1])<<12|(63&e[r+2])<<6|63&e[r+3];if(o>65536&&o<1114112){o-=65536,t.push(String.fromCharCode(o>>>10|55296)),t.push(String.fromCharCode(1023&o|56320)),r+=4;continue}}t.push(String.fromCharCode(65533)),++r}return t.join("")}static _checkContinuation(e,t,r){if(!(t+r<e.length))return!1;for(;r--;)if((192&e[++t])!=128)return!1;return!0}}},59664:function(e,t,r){"use strict";r.d(t,{K:function(){return i},U:function(){return n}});var o=r(776045);let n={PREFIX:`${o.T}-image`},i={DEFAULT_Z_INDEX:1070}},205407:function(e,t,r){"use strict";r.d(t,{Z:function(){return n}}),r(370483);var o=r(36191);class n extends o.Z{init(){let e=this._adapter.getProp("checked"),t=this._adapter.getProp("defaultChecked");this.setChecked(e||t)}setChecked(e){this._adapter.setNativeControlChecked(e)}getChecked(){return this._adapter.getProp("checked")}handleChange(e){let t="checked"in this.getProps(),{checked:r}=e.target,o={target:Object.assign(Object.assign({},this.getProps()),{checked:r}),stopPropagation:()=>{e.stopPropagation()},preventDefault:()=>{e.preventDefault()}};t||this.setChecked(r),this._adapter.notifyChange(o)}destroy(){}constructor(e){super(Object.assign({},e))}}},522805:function(e,t,r){"use strict";r.d(t,{KT:function(){return a},UX:function(){return n},j2:function(){return i}});var o=r(776045);let n={PREFIX:`${o.T}-scrolllist`,SELECTED:`${o.T}-scrolllist-item-selected`},i={MODE:["normal","wheel"]},a={DEFAULT_ITEM_HEIGHT:36,DEFAULT_SCROLL_DURATION:120}},836596:function(e,t,r){"use strict";r(924006),r(877782),r(870128),r(847119),r(19526),r(370483),r(554178),r(469261),r(521291),r(141857),r(207418),r(46163),r(865629),r(295655);var o=r(36191),n=r(245686),i=r(889287),a=r(607707),c=r(170857);let{FILE_STATUS_UPLOADING:s,FILE_STATUS_SUCCESS:G,FILE_STATUS_UPLOAD_FAIL:l,FILE_STATUS_VALID_FAIL:u,FILE_STATUS_WAIT_UPLOAD:d,DRAG_AREA_DEFAULT:T,DRAG_AREA_LEGAL:p,TRIGGER_AUTO:h}=a.j2;class F extends o.Z{init(){this.destroyState=!1;let{disabled:e,addOnPasting:t}=this.getProps();t&&!e&&this.bindPastingHandler()}destroy(){let{disabled:e,addOnPasting:t}=this.getProps();this.releaseMemory(),!e&&this.unbindPastingHandler(),this.destroyState=!0}getError(e){let{action:t,xhr:r,message:o,fileName:n}=e,i=r?r.status:0,a=Error(o||`cannot post ${n} to ${t}, xhr status: ${i}'`);return a.status=i,a.method="post",a.url=t,a}getBody(e){if(!e)return;let t=e.responseText||e.response;if(!t)return t;try{return JSON.parse(t)}catch(e){return t}}checkFileSize(e){let{size:t}=e,{maxSize:r,minSize:o}=this.getProps(),n=!1;return(t>r*c.vr||t<o*c.vr)&&(n=!0),n}handleChange(e){let t=[],{limit:r,transformFile:o,accept:n}=this.getProps(),{fileList:a}=this.getStates(),c=Array.from(e);if(void 0!==n&&(c=c.filter(e=>{let r=this.checkFileFormat(n,e);return!r&&t.push(e),r}),0!==t.length&&this._adapter.notifyAcceptInvalid(t),0===c.length))return;c=c.map(e=>(o&&(e=o(e)),!e.uid&&(e.uid=(0,i.Cd)()),this.checkFileSize(e)&&(e._sizeInvalid=!0,e.status=u,this._adapter.notifySizeError(e,a)),e));let s=a.length+c.length;if(void 0!==r&&s>r){if(this._adapter.notifyExceed(c),1===r){c=c.slice(-1),this._adapter.notifyFileSelect(c),this._adapter.resetInput(),this.replaceFileList(c);return}let e=r-a.length;c=c.slice(0,e)}this._adapter.notifyFileSelect(c),this._adapter.resetInput(),this.addFilesToList(c)}handleReplaceChange(e){if(0===e.length)return;let{transformFile:t,uploadTrigger:r,accept:o}=this.getProps(),{replaceIdx:n,fileList:a}=this.getStates(),c=Array.from(e).pop();if(void 0!==o&&!this.checkFileFormat(o,c)){this._adapter.notifyAcceptInvalid([c]);return}t&&(c=t(c)),!c.uid&&(c.uid=(0,i.Cd)()),this.checkFileSize(c)&&(c._sizeInvalid=!0,c.status=u,this._adapter.notifySizeError(c,a)),this._adapter.notifyFileSelect([c]);let s=this.buildFileItem(c,r),G=[...a];G.splice(n,1,s),this._adapter.notifyChange({currentFile:s,fileList:G}),this._adapter.updateFileList(G,()=>{this._adapter.resetReplaceInput(),!s._sizeInvalid&&this.upload(s)})}buildFileItem(e,t){let{_sizeInvalid:r,status:o}=e;try{delete e._sizeInvalid,delete e.status}catch(e){}let n={status:o||(t===h?s:d),name:e.name,size:(0,c.hR)(e.size),uid:e.uid,percent:0,fileInstance:e,url:this._createURL(e)};return r&&(n._sizeInvalid=!0),this.isImage(e)&&(n.preview=!0),n}replaceFileList(e){let{uploadTrigger:t}=this.getProps(),r=e.map(e=>this.buildFileItem(e,t));this._adapter.notifyChange({fileList:r,currentFile:r[0]}),this._adapter.updateFileList(r,()=>{t===h&&this.startUpload(r)})}addFilesToList(e){let t=this.getState("fileList").slice(),{uploadTrigger:r}=this.getProps(),o=e.map(e=>this.buildFileItem(e,r));o.forEach(e=>{let r=t.findIndex(t=>t.uid===e.uid);-1!==r?t[r]=e:(t.push(e),this._adapter.notifyChange({fileList:t,currentFile:e}))}),this._adapter.updateFileList(t,()=>{r===h&&this.startUpload(o)})}insertFileToList(e,t){let{limit:r,transformFile:o,accept:n,uploadTrigger:a}=this.getProps(),{fileList:c}=this.getStates(),s=[],G=Array.from(e);if(void 0!==n&&(G=G.filter(e=>{let t=this.checkFileFormat(n,e);return!t&&s.push(e),t}),0!==s.length&&this._adapter.notifyAcceptInvalid(s),0===G.length))return;G=G.map(e=>(!e.uid&&(e.uid=(0,i.Cd)()),this.checkFileSize(e)&&(e._sizeInvalid=!0,e.status=u,this._adapter.notifySizeError(e,c)),o&&(e=o(e)),e));let l=c.length+G.length;if(void 0!==r&&l>r){if(1===r){G=G.slice(-1),this._adapter.notifyFileSelect(G),this._adapter.resetInput(),this.replaceFileList(G);return}let e=r-c.length;G=G.slice(0,e),this._adapter.notifyExceed(G)}let d=G.map(e=>this.buildFileItem(e,a)),T=c.slice();void 0!==t?T.splice(t,0,...d):T.push(...d),this._adapter.notifyFileSelect(G),this._adapter.notifyChange({fileList:T,currentFile:null}),this._adapter.updateFileList(T,()=>{a===h&&this.startUpload(d)})}manualUpload(){let e=this.getState("fileList").filter(e=>e.status===d);this.startUpload(e)}startUpload(e){e.forEach(e=>{!e._sizeInvalid&&this.upload(e)})}upload(e){let{beforeUpload:t}=this.getProps();if(void 0===t){this.post(e);return}if("function"==typeof t){let{fileList:t}=this.getStates(),r=this._adapter.notifyBeforeUpload({file:e,fileList:t});switch(!0){case!0===r:this.post(e);break;case!1===r:{let t={shouldUpload:!1,status:a.j2.FILE_STATUS_VALID_FAIL};this.handleBeforeUploadResultInObject(t,e);break}case r&&(0,n.Z)(r):Promise.resolve(r).then(t=>{let r={shouldUpload:!0};"Object"===Object.prototype.toString.call(t).slice(8,-1)&&(r=Object.assign(Object.assign({},r),t)),this.handleBeforeUploadResultInObject(r,e)},t=>{let r={shouldUpload:!1,status:a.j2.FILE_STATUS_VALID_FAIL};"Object"===Object.prototype.toString.call(t).slice(8,-1)&&(r=Object.assign(Object.assign({},r),t)),this.handleBeforeUploadResultInObject(r,e)});break;case"object"==typeof r:this.handleBeforeUploadResultInObject(r,e)}}}handleBeforeUploadResultInObject(e,t){let{shouldUpload:r,status:o,autoRemove:n,validateMessage:i,fileInstance:a}=e,s=this.getState("fileList").slice();if(n)s=s.filter(e=>e.uid!==t.uid);else{let e=this._getFileIndex(t,s);if(e<0)return;o&&(s[e].status=o),i&&(s[e].validateMessage=i),a&&(a.uid=t.uid,s[e].fileInstance=a,s[e].size=(0,c.hR)(a.size),s[e].name=a.name,s[e].url=this._createURL(a)),s[e].shouldUpload=r}this._adapter.updateFileList(s),this._adapter.notifyChange({fileList:s,currentFile:t}),r&&this.post(t)}post(e){let{fileInstance:t}=e,r=this.getProps();if("undefined"==typeof XMLHttpRequest)return;let o=new XMLHttpRequest,n=new FormData,{action:i}=r,{data:a}=r;a&&("function"==typeof a&&(a=a(t)),Object.keys(a).forEach(e=>{n.append(e,a[e])}));let c=r.name||r.fileName||t.name;if(r.customRequest)return r.customRequest({fileName:c,data:a,file:e,fileInstance:t,onProgress:e=>this.handleProgress({e,fileInstance:t}),onError:(e,r)=>this.handleError({e:r,xhr:e,fileInstance:t}),onSuccess:(e,r)=>this.handleSuccess({response:e,fileInstance:t,e:r,isCustomRequest:!0}),withCredentials:r.withCredentials,action:r.action});n.append(c,t),o.open("post",i,!0),r.withCredentials&&"withCredentials"in o&&(o.withCredentials=!0),o.upload&&(o.upload.onprogress=e=>{this.destroyState?o.abort():this.handleProgress({e,fileInstance:t})}),o.onload=e=>{!this.destroyState&&this.handleOnLoad({e,xhr:o,fileInstance:t})},o.onerror=e=>{!this.destroyState&&this.handleError({e,xhr:o,fileInstance:t})};let s=r.headers||{};for(let e in"function"==typeof s&&(s=s(t)),s)Object.prototype.hasOwnProperty.call(s,e)&&null!==s[e]&&o.setRequestHeader(e,s[e]);o.send(n)}handleProgress(e){let{e:t,fileInstance:r}=e,{fileList:o}=this.getStates(),n=o.slice(),i=0;t.total>0&&(i=Number((t.loaded/t.total*100*a.KT.PROGRESS_COEFFICIENT).toFixed(0))||0);let c=this._getFileIndex(r,n);if(!(c<0))n[c].percent=i,n[c].status=s,this._adapter.notifyProgress(i,r,n),this._adapter.updateFileList(n),this._adapter.notifyChange({fileList:n,currentFile:n[c]})}handleOnLoad(e){let{e:t,xhr:r,fileInstance:o}=e,{fileList:n}=this.getStates(),i=this._getFileIndex(o,n);if(!(i<0))r.status<200||r.status>=300?this.handleError({e:t,xhr:r,fileInstance:o}):this.handleSuccess({e:t,xhr:r,fileInstance:o,index:i})}handleSuccess(e){let{e:t,fileInstance:r,isCustomRequest:o=!1,xhr:n,response:i}=e,{fileList:a}=this.getStates(),c=null,s=this._getFileIndex(r,a);if(s<0)return;c=o?i:this.getBody(n);let l=a.slice(),{afterUpload:u}=this.getProps();if(l[s].status=G,l[s].percent=100,this._adapter.notifyProgress(100,r,l),l[s].response=c,t&&(l[s].event=t),u&&"function"==typeof u){let{autoRemove:e,status:t,validateMessage:r,name:o,url:n}=this._adapter.notifyAfterUpload({response:c,file:l[s],fileList:l})||{};t&&(l[s].status=t),r&&(l[s].validateMessage=r),o&&(l[s].name=o),n&&(l[s].url=n),e&&l.splice(s,1)}this._adapter.notifySuccess(c,r,l),this._adapter.notifyChange({fileList:l,currentFile:l[s]}),this._adapter.updateFileList(l)}_getFileIndex(e,t){return t.findIndex(t=>t.uid===e.uid)}handleRemove(e){let{disabled:t}=this.getProps();if(t)return;let{fileList:r}=this.getStates();Promise.resolve(this._adapter.notifyBeforeRemove(e,r)).then(t=>{if(!1===t)return;let o=r.slice(),n=this._getFileIndex(e,r);if(!(n<0))o.splice(n,1),this._adapter.notifyRemove(e.fileInstance,o,e),this._adapter.updateFileList(o),this._adapter.notifyChange({fileList:o,currentFile:e})})}handleError(e){let{e:t,xhr:r,fileInstance:o}=e,{fileList:n}=this.getStates(),i=this._getFileIndex(o,n);if(i<0)return;let{action:a}=this.getProps(),c=n.slice(),s=this.getError({action:a,xhr:r,fileName:o.name});c[i].status=l,c[i].response=s,c[i].event=t,this._adapter.notifyError(s,o,c,r),this._adapter.updateFileList(c),this._adapter.notifyChange({currentFile:c[i],fileList:c})}handleClear(){let{disabled:e}=this.getProps(),{fileList:t}=this.getStates();if(!e)Promise.resolve(this._adapter.notifyBeforeClear(t)).then(e=>{if(!1!==e)this._adapter.updateFileList([]),this._adapter.notifyClear(),this._adapter.notifyChange({fileList:[]})}).catch(e=>{})}_createURL(e){let t=URL.createObjectURL(e),{localUrls:r}=this.getStates(),o=r.slice();return o.push(t),this._adapter.updateLocalUrls(o),t}releaseMemory(){let{localUrls:e}=this.getStates();e.forEach(e=>{this._releaseBlob(e)})}_releaseBlob(e){try{URL.revokeObjectURL(e)}catch(e){}}isImage(e){return/(webp|svg|png|gif|jpg|jpeg|bmp|dpg)$/i.test(e.type)}isMultiple(){return!!this.getProp("multiple")}handleDragEnter(e){e.preventDefault(),e.stopPropagation(),this._dragEnterTarget=e.currentTarget;let{disabled:t}=this.getProps();!t&&this._adapter.updateDragAreaStatus(p)}handleDirectoryDrop(e){var t,r,o,n;return t=this,r=void 0,o=void 0,n=function*(){let t=this.getState("fileList").slice(),r=[].slice.call(e.dataTransfer.items),o=yield(0,c.D)(r);this.handleChange(o),this._adapter.updateDragAreaStatus(T),this._adapter.notifyDrop(e,o,t)},new(o||(o=Promise))(function(e,i){function a(e){try{s(n.next(e))}catch(e){i(e)}}function c(e){try{s(n.throw(e))}catch(e){i(e)}}function s(t){var r;t.done?e(t.value):((r=t.value)instanceof o?r:new o(function(e){e(r)})).then(a,c)}s((n=n.apply(t,r||[])).next())})}handleDrop(e){e.preventDefault(),e.stopPropagation();let{disabled:t,directory:r}=this.getProps(),o=this.getState("fileList").slice();if(!t){if(r){this.handleDirectoryDrop(e);return}let t=Array.from(e.dataTransfer.files);this.handleChange(t),this._adapter.updateDragAreaStatus(T),this._adapter.notifyDrop(e,t,o)}}handleDragOver(e){e.preventDefault(),e.stopPropagation()}handleDragLeave(e){e.preventDefault(),e.stopPropagation(),this._dragEnterTarget===e.target&&this._adapter.updateDragAreaStatus(T)}checkFileFormat(e,t){let r=e.split(",").map(e=>e.trim()).filter(e=>e),o=t.type||"",n=o.replace(/\/.*$/,"");return r.some(e=>{if("."===e.charAt(0)){let r=t.name||"",o=e.split(".").pop().toLowerCase();return(0,c.pn)(r.toLowerCase(),o)}return/\/\*$/.test(e)?n===e.replace(/\/.*$/,""):!!/^[^\/]+\/[^\/]+$/.test(e)&&o===e})}retry(e){let{onRetry:t}=this.getProps();t&&"function"==typeof t&&t(e),this.post(e)}handlePreviewClick(e){this._adapter.notifyPreviewClick(e)}readFileFromClipboard(e){for(let t of e)for(let e of t.types)e.startsWith("image")&&t.getType(e).then(e=>e.arrayBuffer()).then(t=>{let r=e.split("/")[1],o=new File([t],`upload.${r}`,{type:e});this.handleChange([o])})}handlePasting(e){let t=this._adapter.isMac()?e.metaKey:e.ctrlKey,{addOnPasting:r}=this.getProps();r&&t&&"KeyV"===e.code&&navigator.permissions.query({name:"clipboard-read"}).then(e=>{"granted"===e.state||"prompt"===e.state?navigator.clipboard.read().then(e=>{this.readFileFromClipboard(e)}):this._adapter.notifyPastingError(e)}).catch(e=>{this._adapter.notifyPastingError(e)})}bindPastingHandler(){this._adapter.registerPastingHandler(e=>this.handlePasting(e))}unbindPastingHandler(){this._adapter.unRegisterPastingHandler()}constructor(e){super(Object.assign({},e)),this.destroyState=!1}}t.Z=F},591264:function(e,t,r){"use strict";r.d(t,{KT:function(){return a},UX:function(){return n},j2:function(){return i}});var o=r(776045);let n={PREFIX:`${o.T}-userGuide`,PREFIX_MODAL:`${o.T}-userGuide-modal`},i={MODE:["popup","modal"],POSITION_SET:["top","topLeft","topRight","left","leftTop","leftBottom","right","rightTop","rightBottom","bottom","bottomLeft","bottomRight","leftTopOver","rightTopOver"],THEME:["default","primary"]},a={DEFAULT_CURRENT:0,DEFAULT_SPOTLIGHT_PADDING:5,DEFAULT_Z_INDEX:1030}},510786:function(e,t,r){"use strict";r(870128),r(847119);var o=r(711521),n=r.n(o),i=r(787007);class a{get enable(){return this._enable}set enable(e){this._enable=e}static getFocusableElements(e){if(!(0,i.Z)(e))return[];let t="input:not([disabled]):not([tabindex='-1']),textarea:not([disabled]):not([tabindex='-1']),button:not([disabled]):not([tabindex='-1']),a[href]:not([tabindex='-1']),select:not([disabled]):not([tabindex='-1']),area[href]:not([tabindex='-1']),iframe:not([tabindex='-1']),object:not([tabindex='-1']),*[tabindex]:not([tabindex='-1']),*[contenteditable]:not([tabindex='-1'])";return Array.from(e.querySelectorAll(t))}static getActiveElement(){return document?document.activeElement:null}constructor(e,t){var r;this.addFocusRedirectListener=e=>(this.focusRedirectListenerList.push(e),()=>this.removeFocusRedirectListener(e)),this.removeFocusRedirectListener=e=>{this.focusRedirectListenerList=n()(this.focusRedirectListenerList,e)},this.destroy=()=>{var e;null===(e=this.container)||void 0===e||e.removeEventListener("keydown",this.onKeyPress)},this.shouldFocusRedirect=e=>{if(!this.enable)return!1;for(let t of this.focusRedirectListenerList)if(!t(e))return!1;return!0},this.focusElement=(e,t)=>{let{preventScroll:r}=this.options;null==e||e.focus({preventScroll:r}),t.preventDefault()},this.onKeyPress=e=>{if(e&&"Tab"===e.key){let t=a.getFocusableElements(this.container);t.length&&(e.shiftKey?this.handleContainerShiftTabKeyDown(t,e):this.handleContainerTabKeyDown(t,e))}},this.handleContainerTabKeyDown=(e,t)=>{let r=a.getActiveElement(),o=e[e.length-1]===r,n=e[0];o&&this.shouldFocusRedirect(n)&&this.focusElement(n,t)},this.handleContainerShiftTabKeyDown=(e,t)=>{let r=a.getActiveElement(),o=e[0]===r,n=e[e.length-1];o&&this.shouldFocusRedirect(n)&&this.focusElement(n,t)},Object.freeze(t),this.container=e,this.options=t,this.enable=null===(r=null==t?void 0:t.enable)||void 0===r||r,this.focusRedirectListenerList=(null==t?void 0:t.onFocusRedirectListener)?Array.isArray(t.onFocusRedirectListener)?[...t.onFocusRedirectListener]:[t.onFocusRedirectListener]:[],this.container.addEventListener("keydown",this.onKeyPress)}}t.Z=a},869358:function(e,t,r){"use strict";function o(e){return null==e}r.d(t,{Z:function(){return o}})},625059:function(e,t,r){"use strict";r(847119);var o=r(977353),n=r.n(o),i=r(267034);t.Z=function(e){if("development"===n()(i,"env.NODE_ENV"))for(var t=arguments.length,r=Array(t>1?t-1:0),o=1;o<t;o++)r[o-1]=arguments[o]}},237073:function(e,t,r){"use strict";function o(e,t){}r.d(t,{Z:function(){return o}})},471630:function(e,t,r){"use strict";r(370483);var o=r(703196);function n(){return(n=Object.assign||function(e){for(var t=1;t<arguments.length;t++){var r=arguments[t];for(var o in r)Object.prototype.hasOwnProperty.call(r,o)&&(e[o]=r[o])}return e}).apply(this,arguments)}let i=o.forwardRef(function(e,t){return o.createElement("svg",n({viewBox:"0 0 32 32",fill:"none",xmlns:"http://www.w3.org/2000/svg",width:"1em",height:"1em",focusable:!1,ref:t},e),o.createElement("path",{d:"M23.5 15.134C24.1667 15.5189 24.1667 16.4811 23.5 16.866L12.25 23.3612C11.5833 23.7461 10.75 23.265 10.75 22.4952L10.75 9.50481C10.75 8.73501 11.5833 8.25388 12.25 8.63878L23.5 15.134Z",fill:"currentColor"}))});i.elementType="Icon",t.Z=i},118971:function(e,t,r){"use strict";var o=r(258343),n=r(575562),i=r(174112),a=r(988402),c=r(703196),s=r(536961);(0,r(945054).n)(e=>{let{playerRef:t}=(0,c.useContext)(a.E),r=(0,c.useRef)();return(0,c.useEffect)(()=>{let e=t.current;return e.defineProperty("changeDefinition",{configurable:!0,value(e){var t;null===(t=r.current)||void 0===t||t.changeDefinition(e)}}),e.defineProperty("curDefinition",{configurable:!0,get(){var e;return null===(e=r.current)||void 0===e?void 0:e.getCurrentDefinition()}}),()=>{let e=t.current;if(!!e)e.removeProperty("changeDefinition"),e.removeProperty("curDefinition")}},[]),(0,i.jsx)(s.w,(0,n._)((0,o._)({},e),{ref:r}))})},769078:function(e,t,r){"use strict";r.d(t,{C4:function(){return o.C4},D2:function(){return o.D2},Eo:function(){return o.Eo},FP:function(){return i.F},GI:function(){return o.GI},J5:function(){return n.J5},PZ:function(){return a.PZ},Sp:function(){return o.Sp},Sy:function(){return a.Sy},V2:function(){return o.V2},Zv:function(){return o.Zv},b$:function(){return o.b$},di:function(){return a.di},le:function(){return s.l},lp:function(){return o.lp},ry:function(){return o.ry},tF:function(){return n.tF},um:function(){return o.um},w2:function(){return c.w},wW:function(){return i.w}});var o=r(232208),n=r(361021),i=r(406066),a=r(245518),c=r(849387),s=r(352324)},260545:function(e,t,r){"use strict";r.d(t,{N:function(){return a},d:function(){return i}});var o=r(203687);r(847119);var n=r(641969);class i extends n.S{constructor(...e){super(...e),(0,o._)(this,"el",void 0)}}let a=e=>e instanceof i},186549:function(e,t,r){"use strict";r.d(t,{e:function(){return n}});var o=r(563873);function n(e){return(0,o.getDependencyTree)(e)}},275909:function(e,t,r){"use strict";r.d(t,{_:function(){return n}});var o=r(75356);function n(e,t){if(null==e)return{};var r,n,i=(0,o._)(e,t);if(Object.getOwnPropertySymbols){var a=Object.getOwnPropertySymbols(e);for(n=0;n<a.length;n++){if(r=a[n],!(t.indexOf(r)>=0))Object.prototype.propertyIsEnumerable.call(e,r)&&(i[r]=e[r])}}return i}},693520:function(e,t,r){"use strict";r.d(t,{_:function(){return i}});var o=r(68533),n=r(503415);function i(e){var t=(0,o._)(e,"string");return"symbol"===(0,n._)(t)?t:String(t)}},299920:function(e,t,r){"use strict";function o(e,t){let r={type:"Block",value:e.value};t.inherit(e,r),t.comments.push(r);let o={type:"JSXEmptyExpression",comments:[Object.assign({},r,{leading:!1,trailing:!0})]};t.patch(e,o);let n={type:"JSXExpressionContainer",expression:o};return t.patch(e,n),n}r.d(t,{U:function(){return o}})},715505:function(e,t,r){"use strict";r.d(t,{n:function(){return n}});var o=r(274020);function n(e,t){let r;let n=e.data&&e.data.estree,i=n&&n.comments||[];n&&(t.comments.push(...i),(0,o.S)(n,n.comments),r=n.body[0]&&"ExpressionStatement"===n.body[0].type&&n.body[0].expression||void 0),!r&&(r={type:"JSXEmptyExpression"},t.patch(e,r));let a={type:"JSXExpressionContainer",expression:r};return t.inherit(e,a),a}},268050:function(e,t,r){"use strict";r.d(t,{D:function(){return n}});var o=r(639735);function n(e,t,r,n){let i=(0,o.l)(r),a='"'===i?"Quote":"Apostrophe",c=r.enter("definition"),s=r.enter("label"),G=r.createTracker(n),l=G.move("[");return l+=G.move(r.safe(r.associationId(e),{before:l,after:"]",...G.current()})),l+=G.move("]: "),s(),!e.url||/[\0- \u007F]/.test(e.url)?(s=r.enter("destinationLiteral"),l+=G.move("<"),l+=G.move(r.safe(e.url,{before:l,after:">",...G.current()}))+G.move(">")):(s=r.enter("destinationRaw"),l+=G.move(r.safe(e.url,{before:l,after:e.title?" ":"\n",...G.current()}))),s(),e.title&&(s=r.enter(`title${a}`),l+=G.move(" "+i),l+=G.move(r.safe(e.title,{before:l,after:i,...G.current()}))+G.move(i),s()),c(),l}},725098:function(e,t,r){"use strict";r.d(t,{k:function(){return o}});class o{constructor(e,t){this.attribute=t,this.property=e}}o.prototype.attribute="",o.prototype.booleanish=!1,o.prototype.boolean=!1,o.prototype.commaOrSpaceSeparated=!1,o.prototype.commaSeparated=!1,o.prototype.defined=!1,o.prototype.mustUseProperty=!1,o.prototype.number=!1,o.prototype.overloadedBoolean=!1,o.prototype.property="",o.prototype.spaceSeparated=!1,o.prototype.space=void 0},165320:function(e,t,r){"use strict";r.d(t,{q:function(){return i}});var o=r(392441),n=r(151419);function i(e,t){return(0,o.v)(e,Object.assign({format:n.C},t))}},417204:function(e,t,r){"use strict";function o(){return(o=Object.assign?Object.assign.bind():function(e){for(var t=1;t<arguments.length;t++){var r=arguments[t];for(var o in r)Object.prototype.hasOwnProperty.call(r,o)&&(e[o]=r[o])}return e}).apply(this,arguments)}r.d(t,{c:function(){return c},p:function(){return l}}),r(370483),r(877782),r(642530),r(207418),r(870128),r(796939),r(19526);var n={Pop:"POP",Push:"PUSH",Replace:"REPLACE"},i=function(e){return e},a="beforeunload";function c(e){void 0===e&&(e={});var t=e.window,r=void 0===t?document.defaultView:t,c=r.history;function u(){var e=r.location,t=e.pathname,o=e.search,n=e.hash,a=c.state||{};return[a.idx,i({pathname:t,search:o,hash:n,state:a.usr||null,key:a.key||"default"})]}var d=null;r.addEventListener("popstate",function(){if(d)g.call(d),d=null;else{var e=n.Pop,t=u(),r=t[0],o=t[1];if(g.length){if(null!=r){var i=h-r;i&&(d={action:e,location:o,retry:function(){b(-1*i)}},b(i))}}else y(e)}});var T=n.Pop,p=u(),h=p[0],F=p[1],f=G(),g=G();function X(e){return"string"==typeof e?e:function(e){var t=e.pathname,r=void 0===t?"/":t,o=e.search,n=void 0===o?"":o,i=e.hash,a=void 0===i?"":i;return n&&"?"!==n&&(r+="?"===n.charAt(0)?n:"?"+n),a&&"#"!==a&&(r+="#"===a.charAt(0)?a:"#"+a),r}(e)}function M(e,t){return void 0===t&&(t=null),i(o({pathname:F.pathname,hash:"",search:""},"string"==typeof e?l(e):e,{state:t,key:function(){return Math.random().toString(36).substr(2,8)}()}))}function m(e,t){return[{usr:e.state,key:e.key,idx:t},X(e)]}function v(e,t,r){return!g.length||(g.call({action:e,location:t,retry:r}),!1)}function y(e){T=e;var t=u();h=t[0],F=t[1],f.call({action:T,location:F})}null==h&&(h=0,c.replaceState(o({},c.state,{idx:h}),""));function b(e){c.go(e)}return{get action(){return T},get location(){return F},createHref:X,push:function e(t,o){var i=n.Push,a=M(t,o);if(v(i,a,function(){e(t,o)})){var s=m(a,h+1),G=s[0],l=s[1];try{c.pushState(G,"",l)}catch(e){r.location.assign(l)}y(i)}},replace:function e(t,r){var o=n.Replace,i=M(t,r);if(v(o,i,function(){e(t,r)})){var a=m(i,h),s=a[0],G=a[1];c.replaceState(s,"",G),y(o)}},go:b,back:function(){b(-1)},forward:function(){b(1)},listen:function(e){return f.push(e)},block:function(e){var t=g.push(e);return 1===g.length&&r.addEventListener(a,s),function(){t(),!g.length&&r.removeEventListener(a,s)}}}}function s(e){e.preventDefault(),e.returnValue=""}function G(){var e=[];return{get length(){return e.length},push:function(t){return e.push(t),function(){e=e.filter(function(e){return e!==t})}},call:function(t){e.forEach(function(e){return e&&e(t)})}}}function l(e){var t={};if(e){var r=e.indexOf("#");r>=0&&(t.hash=e.substr(r),e=e.substr(0,r));var o=e.indexOf("?");o>=0&&(t.search=e.substr(o),e=e.substr(0,o)),e&&(t.pathname=e)}return t}}}]);