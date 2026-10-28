import { useCallback, useEffect, useState } from "react";

/** F24 — the phone pages (/sos, /safe, /find) in English, Hindi, Tamil, Bengali
 * and Assamese. Non-English texts are machine-drafted and `reviewed: false`
 * until a native speaker checks them; the page says so and nothing is presented
 * as an official translation. Values sent to the server stay English codes. */
export const LANGS = {
  en: { name: "English", reviewed: true },
  hi: { name: "हिन्दी", reviewed: false },
  ta: { name: "தமிழ்", reviewed: false },
  bn: { name: "বাংলা", reviewed: false },
  as: { name: "অসমীয়া", reviewed: false },
};

const WATER_CODES = ["ankle-deep", "knee-deep", "waist-deep", "chest-deep", "water rising fast"];
export { WATER_CODES };

export const DICT = {
  en: {
    lang: "Language",
    unreviewed: "",
    title: "Ask for rescue",
    name: "Your name",
    age: "Age",
    people: "People with you",
    water: "Water where you are",
    water_opts: ["ankle-deep", "knee-deep", "waist-deep", "chest-deep", "water rising fast"],
    injured: "Is anyone injured?",
    med_opts: ["No one is hurt", "Someone is injured", "Someone is badly hurt / unconscious"],
    locate: "📍 Share my location",
    locating: "Finding you…",
    photo: "Photo of the water (optional)",
    send: "🆘 Send SOS",
    sending: "Sending…",
    foot: "Your name, location and photo go only to the rescue control room of the live operation. Demo service — in a real emergency also call the official helpline.",
    err_name: "Please enter your name.",
    err_people: "People with you must be 1 to 50.",
    err_age: "Age must be 0 to 120.",
    err_pos: "Share your location or place the pin on the map first.",
    err_409: "No live rescue operation is running right now.",
    err_429: "Too many SOS sent from this phone — please wait a minute.",
    err_send: "Could not send — check your connection and try again.",
    loc_denied: "Location permission denied — tap the map or drag the pin to where you are.",
    loc_failed: "Could not get your location — tap the map or drag the pin to where you are.",
    loc_unsupported: "This browser cannot share location — tap the map to place the pin where you are.",
    loc_found: "Location found (±{m} m). Drag the pin if it is not exact.",
    offline: "📶 No connection — your SOS is saved on this phone and will be sent automatically as soon as the network is back. Keep this page open if you can.",
    your_sos: "YOUR SOS",
    steps: ["Waiting", "Unit on the way", "Going to shelter", "Safe"],
    stay: "Stay where you are if it is safe. This page updates every 5 seconds.",
    another: "Send another SOS",
    share: "🔗 Share with family",
    share_note: "Only people with this link can see your status:",
    safe_at: "Safe at",
    shelter: "Shelter",
    sms: "✉️ Send by SMS (no internet)",
    sms_note: "Opens your SMS app with a short message to the rescue number. Normal SMS charges may apply.",
    safe_title: "Am I safe?",
    safe_locate: "📍 Check my area",
    nearest_shelter: "NEAREST OPEN SHELTER WITH SEATS",
    nearest_hospital: "NEAREST HOSPITAL (OPENSTREETMAP)",
    roads_near: "ROADS NEAR YOU",
    no_shelter: "No open shelter has free seats right now.",
  },
  hi: {
    lang: "भाषा",
    unreviewed: "मशीन से बना अनुवाद — अभी किसी मूल भाषी ने जाँचा नहीं है।",
    title: "बचाव के लिए अनुरोध करें",
    name: "आपका नाम",
    age: "उम्र",
    people: "आपके साथ कितने लोग",
    water: "आपके पास पानी कितना है",
    water_opts: ["टखने तक", "घुटने तक", "कमर तक", "छाती तक", "पानी तेज़ी से बढ़ रहा है"],
    injured: "क्या कोई घायल है?",
    med_opts: ["कोई घायल नहीं", "कोई घायल है", "कोई गंभीर रूप से घायल / बेहोश है"],
    locate: "📍 मेरी लोकेशन भेजें",
    locating: "आपको खोज रहे हैं…",
    photo: "पानी की फ़ोटो (वैकल्पिक)",
    send: "🆘 SOS भेजें",
    sending: "भेजा जा रहा है…",
    foot: "आपका नाम, लोकेशन और फ़ोटो केवल चल रहे बचाव अभियान के कंट्रोल रूम को जाते हैं। यह डेमो सेवा है — असली आपात स्थिति में आधिकारिक हेल्पलाइन पर भी कॉल करें।",
    err_name: "कृपया अपना नाम लिखें।",
    err_people: "साथ के लोग 1 से 50 के बीच होने चाहिए।",
    err_age: "उम्र 0 से 120 के बीच होनी चाहिए।",
    err_pos: "पहले अपनी लोकेशन भेजें या नक्शे पर पिन लगाएँ।",
    err_409: "अभी कोई बचाव अभियान नहीं चल रहा है।",
    err_429: "इस फ़ोन से बहुत सारे SOS भेजे गए — कृपया एक मिनट रुकें।",
    err_send: "भेजा नहीं जा सका — कनेक्शन जाँचें और फिर कोशिश करें।",
    loc_denied: "लोकेशन की अनुमति नहीं मिली — नक्शे पर टैप करें या पिन को अपनी जगह खींचें।",
    loc_failed: "आपकी लोकेशन नहीं मिल सकी — नक्शे पर टैप करें या पिन को अपनी जगह खींचें।",
    loc_unsupported: "यह ब्राउज़र लोकेशन नहीं भेज सकता — नक्शे पर टैप करके पिन लगाएँ।",
    loc_found: "लोकेशन मिल गई (±{m} मी)। अगर सही न हो तो पिन खींचें।",
    offline: "📶 नेटवर्क नहीं है — आपका SOS इस फ़ोन में सेव है और नेटवर्क आते ही अपने-आप भेज दिया जाएगा। हो सके तो यह पेज खुला रखें।",
    your_sos: "आपका SOS",
    steps: ["इंतज़ार", "टीम रास्ते में है", "शेल्टर जा रहे हैं", "सुरक्षित"],
    stay: "अगर सुरक्षित हो तो वहीं रहें। यह पेज हर 5 सेकंड में अपडेट होता है।",
    another: "एक और SOS भेजें",
    share: "🔗 परिवार के साथ साझा करें",
    share_note: "केवल इस लिंक वाले लोग आपकी स्थिति देख सकते हैं:",
    safe_at: "सुरक्षित पहुँचे:",
    shelter: "शेल्टर",
    sms: "✉️ SMS से भेजें (इंटरनेट नहीं)",
    sms_note: "आपका SMS ऐप बचाव नंबर के लिए छोटे संदेश के साथ खुलेगा। सामान्य SMS शुल्क लग सकता है।",
    safe_title: "क्या मैं सुरक्षित हूँ?",
    safe_locate: "📍 मेरी लोकेशन इस्तेमाल करें",
    nearest_shelter: "सबसे नज़दीकी खुला शेल्टर (सीटें उपलब्ध)",
    nearest_hospital: "सबसे नज़दीकी अस्पताल (OpenStreetMap)",
    roads_near: "आपके पास की सड़कें",
    no_shelter: "अभी किसी खुले शेल्टर में सीट खाली नहीं है।",
  },
  ta: {
    lang: "மொழி",
    unreviewed: "இயந்திர மொழிபெயர்ப்பு — தாய்மொழி பேசுபவர் இன்னும் சரிபார்க்கவில்லை.",
    title: "மீட்பு உதவி கேளுங்கள்",
    name: "உங்கள் பெயர்",
    age: "வயது",
    people: "உங்களுடன் உள்ளவர்கள்",
    water: "நீங்கள் இருக்கும் இடத்தில் தண்ணீர்",
    water_opts: ["கணுக்கால் அளவு", "முழங்கால் அளவு", "இடுப்பு அளவு", "மார்பு அளவு", "தண்ணீர் வேகமாக உயர்கிறது"],
    injured: "யாராவது காயமடைந்துள்ளார்களா?",
    med_opts: ["யாருக்கும் காயம் இல்லை", "ஒருவர் காயமடைந்துள்ளார்", "ஒருவர் பலத்த காயம் / மயக்கம்"],
    locate: "📍 என் இருப்பிடத்தைப் பகிர்",
    locating: "உங்களைத் தேடுகிறோம்…",
    photo: "தண்ணீரின் புகைப்படம் (விருப்பம்)",
    send: "🆘 SOS அனுப்பு",
    sending: "அனுப்புகிறது…",
    foot: "உங்கள் பெயர், இருப்பிடம் மற்றும் புகைப்படம் நடப்பு மீட்பு நடவடிக்கையின் கட்டுப்பாட்டு அறைக்கு மட்டுமே செல்லும். இது ஒரு டெமோ சேவை — உண்மையான அவசரத்தில் அதிகாரப்பூர்வ உதவி எண்ணையும் அழைக்கவும்.",
    err_name: "உங்கள் பெயரை உள்ளிடவும்.",
    err_people: "உடன் உள்ளவர்கள் 1 முதல் 50 வரை இருக்க வேண்டும்.",
    err_age: "வயது 0 முதல் 120 வரை இருக்க வேண்டும்.",
    err_pos: "முதலில் உங்கள் இருப்பிடத்தைப் பகிரவும் அல்லது வரைபடத்தில் குறியிடவும்.",
    err_409: "இப்போது எந்த மீட்பு நடவடிக்கையும் நடைபெறவில்லை.",
    err_429: "இந்த தொலைபேசியிலிருந்து அதிக SOS அனுப்பப்பட்டுள்ளது — ஒரு நிமிடம் காத்திருக்கவும்.",
    err_send: "அனுப்ப முடியவில்லை — இணைப்பைச் சரிபார்த்து மீண்டும் முயற்சிக்கவும்.",
    loc_denied: "இருப்பிட அனுமதி மறுக்கப்பட்டது — வரைபடத்தைத் தட்டவும் அல்லது குறியை உங்கள் இடத்துக்கு இழுக்கவும்.",
    loc_failed: "உங்கள் இருப்பிடம் கிடைக்கவில்லை — வரைபடத்தைத் தட்டவும் அல்லது குறியை இழுக்கவும்.",
    loc_unsupported: "இந்த உலாவி இருப்பிடத்தைப் பகிர முடியாது — வரைபடத்தைத் தட்டி குறியிடவும்.",
    loc_found: "இருப்பிடம் கிடைத்தது (±{m} மீ). சரியாக இல்லையெனில் குறியை இழுக்கவும்.",
    offline: "📶 இணைப்பு இல்லை — உங்கள் SOS இந்த தொலைபேசியில் சேமிக்கப்பட்டுள்ளது, இணைப்பு வந்தவுடன் தானாக அனுப்பப்படும். முடிந்தால் இந்தப் பக்கத்தைத் திறந்தே வைத்திருங்கள்.",
    your_sos: "உங்கள் SOS",
    steps: ["காத்திருக்கிறது", "குழு வருகிறது", "முகாமுக்குச் செல்கிறது", "பாதுகாப்பு"],
    stay: "பாதுகாப்பாக இருந்தால் அங்கேயே இருங்கள். இந்தப் பக்கம் 5 வினாடிகளுக்கு ஒருமுறை புதுப்பிக்கப்படும்.",
    another: "மற்றொரு SOS அனுப்பு",
    share: "🔗 குடும்பத்துடன் பகிர்",
    share_note: "இந்த இணைப்பு உள்ளவர்கள் மட்டுமே உங்கள் நிலையைப் பார்க்க முடியும்:",
    safe_at: "பாதுகாப்பாக உள்ள இடம்:",
    shelter: "முகாம்",
    sms: "✉️ SMS மூலம் அனுப்பு (இணையம் இல்லை)",
    sms_note: "உங்கள் SMS செயலி மீட்பு எண்ணுக்கான சிறு செய்தியுடன் திறக்கும். வழக்கமான SMS கட்டணம் இருக்கலாம்.",
    safe_title: "நான் பாதுகாப்பாக இருக்கிறேனா?",
    safe_locate: "📍 என் இருப்பிடத்தைப் பயன்படுத்து",
    nearest_shelter: "இடம் உள்ள அருகிலுள்ள திறந்த முகாம்",
    nearest_hospital: "அருகிலுள்ள மருத்துவமனை (OpenStreetMap)",
    roads_near: "உங்கள் அருகிலுள்ள சாலைகள்",
    no_shelter: "இப்போது எந்தத் திறந்த முகாமிலும் இடம் இல்லை.",
  },
  bn: {
    lang: "ভাষা",
    unreviewed: "যন্ত্রে তৈরি অনুবাদ — এখনও কোনো মাতৃভাষী যাচাই করেননি।",
    title: "উদ্ধারের জন্য অনুরোধ করুন",
    name: "আপনার নাম",
    age: "বয়স",
    people: "আপনার সাথে কতজন",
    water: "আপনার কাছে জলের অবস্থা",
    water_opts: ["গোড়ালি পর্যন্ত", "হাঁটু পর্যন্ত", "কোমর পর্যন্ত", "বুক পর্যন্ত", "জল দ্রুত বাড়ছে"],
    injured: "কেউ কি আহত?",
    med_opts: ["কেউ আহত নয়", "কেউ আহত", "কেউ গুরুতর আহত / অজ্ঞান"],
    locate: "📍 আমার অবস্থান পাঠান",
    locating: "আপনাকে খোঁজা হচ্ছে…",
    photo: "জলের ছবি (ঐচ্ছিক)",
    send: "🆘 SOS পাঠান",
    sending: "পাঠানো হচ্ছে…",
    foot: "আপনার নাম, অবস্থান ও ছবি শুধুমাত্র চলমান উদ্ধার অভিযানের কন্ট্রোল রুমে যায়। এটি একটি ডেমো পরিষেবা — প্রকৃত জরুরি অবস্থায় সরকারি হেল্পলাইনেও ফোন করুন।",
    err_name: "অনুগ্রহ করে আপনার নাম লিখুন।",
    err_people: "সাথের লোকসংখ্যা ১ থেকে ৫০ হতে হবে।",
    err_age: "বয়স ০ থেকে ১২০ হতে হবে।",
    err_pos: "আগে আপনার অবস্থান পাঠান বা মানচিত্রে পিন বসান।",
    err_409: "এখন কোনো উদ্ধার অভিযান চলছে না।",
    err_429: "এই ফোন থেকে অনেক SOS পাঠানো হয়েছে — এক মিনিট অপেক্ষা করুন।",
    err_send: "পাঠানো যায়নি — সংযোগ পরীক্ষা করে আবার চেষ্টা করুন।",
    loc_denied: "অবস্থানের অনুমতি দেওয়া হয়নি — মানচিত্রে ট্যাপ করুন বা পিনটি আপনার জায়গায় টেনে আনুন।",
    loc_failed: "আপনার অবস্থান পাওয়া যায়নি — মানচিত্রে ট্যাপ করুন বা পিনটি টেনে আনুন।",
    loc_unsupported: "এই ব্রাউজার অবস্থান পাঠাতে পারে না — মানচিত্রে ট্যাপ করে পিন বসান।",
    loc_found: "অবস্থান পাওয়া গেছে (±{m} মি)। ঠিক না হলে পিনটি টেনে সরান।",
    offline: "📶 সংযোগ নেই — আপনার SOS এই ফোনে সংরক্ষিত আছে এবং নেটওয়ার্ক ফিরলেই নিজে থেকে পাঠানো হবে। সম্ভব হলে এই পাতা খোলা রাখুন।",
    your_sos: "আপনার SOS",
    steps: ["অপেক্ষা", "দল আসছে", "আশ্রয়ে যাচ্ছে", "নিরাপদ"],
    stay: "নিরাপদ হলে যেখানে আছেন সেখানেই থাকুন। এই পাতা প্রতি ৫ সেকেন্ডে হালনাগাদ হয়।",
    another: "আরেকটি SOS পাঠান",
    share: "🔗 পরিবারের সাথে শেয়ার করুন",
    share_note: "শুধু এই লিঙ্ক যাঁদের কাছে আছে তাঁরাই আপনার অবস্থা দেখতে পারবেন:",
    safe_at: "নিরাপদে পৌঁছেছেন:",
    shelter: "আশ্রয়কেন্দ্র",
    sms: "✉️ SMS-এ পাঠান (ইন্টারনেট নেই)",
    sms_note: "আপনার SMS অ্যাপ উদ্ধার নম্বরে একটি ছোট বার্তা সহ খুলবে। সাধারণ SMS খরচ লাগতে পারে।",
    safe_title: "আমি কি নিরাপদ?",
    safe_locate: "📍 আমার অবস্থান ব্যবহার করুন",
    nearest_shelter: "সবচেয়ে কাছের খোলা আশ্রয়কেন্দ্র (জায়গা আছে)",
    nearest_hospital: "সবচেয়ে কাছের হাসপাতাল (OpenStreetMap)",
    roads_near: "আপনার কাছের রাস্তা",
    no_shelter: "এখন কোনো খোলা আশ্রয়কেন্দ্রে জায়গা নেই।",
  },
  as: {
    lang: "ভাষা",
    unreviewed: "যন্ত্ৰৰে প্ৰস্তুত কৰা অনুবাদ — এতিয়াও কোনো মাতৃভাষীয়ে পৰীক্ষা কৰা নাই।",
    title: "উদ্ধাৰৰ বাবে অনুৰোধ কৰক",
    name: "আপোনাৰ নাম",
    age: "বয়স",
    people: "আপোনাৰ লগত কিমানজন",
    water: "আপোনাৰ ওচৰত পানীৰ অৱস্থা",
    water_opts: ["গাঁঠিলৈকে", "আঁঠুলৈকে", "কঁকাললৈকে", "বুকুলৈকে", "পানী খৰকৈ বাঢ়িছে"],
    injured: "কোনোবা আহত হৈছে নেকি?",
    med_opts: ["কোনো আহত হোৱা নাই", "কোনোবা আহত", "কোনোবা গুৰুতৰভাৱে আহত / অচেতন"],
    locate: "📍 মোৰ অৱস্থান পঠিয়াওক",
    locating: "আপোনাক বিচাৰি আছোঁ…",
    photo: "পানীৰ ফটো (ঐচ্ছিক)",
    send: "🆘 SOS পঠিয়াওক",
    sending: "পঠিওৱা হৈছে…",
    foot: "আপোনাৰ নাম, অৱস্থান আৰু ফটো কেৱল চলি থকা উদ্ধাৰ অভিযানৰ নিয়ন্ত্ৰণ কক্ষলৈহে যায়। এইটো এটা ডেমো সেৱা — প্ৰকৃত জৰুৰীকালীন অৱস্থাত চৰকাৰী হেল্পলাইনতো ফোন কৰক।",
    err_name: "অনুগ্ৰহ কৰি আপোনাৰ নাম লিখক।",
    err_people: "লগৰ মানুহৰ সংখ্যা ১ৰ পৰা ৫০ ৰ ভিতৰত হ'ব লাগিব।",
    err_age: "বয়স ০ৰ পৰা ১২০ ৰ ভিতৰত হ'ব লাগিব।",
    err_pos: "প্ৰথমে আপোনাৰ অৱস্থান পঠিয়াওক বা মানচিত্ৰত পিন বহুৱাওক।",
    err_409: "এতিয়া কোনো উদ্ধাৰ অভিযান চলি থকা নাই।",
    err_429: "এই ফোনৰ পৰা বহুত SOS পঠিওৱা হৈছে — অনুগ্ৰহ কৰি এক মিনিট অপেক্ষা কৰক।",
    err_send: "পঠিয়াব পৰা নগ'ল — সংযোগ পৰীক্ষা কৰি পুনৰ চেষ্টা কৰক।",
    loc_denied: "অৱস্থানৰ অনুমতি দিয়া হোৱা নাই — মানচিত্ৰত টিপক বা পিনটো আপোনাৰ ঠাইলৈ টানি আনক।",
    loc_failed: "আপোনাৰ অৱস্থান পোৱা নগ'ল — মানচিত্ৰত টিপক বা পিনটো টানি আনক।",
    loc_unsupported: "এই ব্ৰাউজাৰে অৱস্থান পঠিয়াব নোৱাৰে — মানচিত্ৰত টিপি পিন বহুৱাওক।",
    loc_found: "অৱস্থান পোৱা গ'ল (±{m} মি)। শুদ্ধ নহ'লে পিনটো টানি ঠিক কৰক।",
    offline: "📶 সংযোগ নাই — আপোনাৰ SOS এই ফোনত সংৰক্ষিত আছে আৰু নেটৱৰ্ক ঘূৰি অহাৰ লগে লগে নিজে নিজে পঠিওৱা হ'ব। পাৰিলে এই পৃষ্ঠাটো খুলি ৰাখক।",
    your_sos: "আপোনাৰ SOS",
    steps: ["অপেক্ষা", "দল আহি আছে", "আশ্ৰয়লৈ গৈ আছে", "সুৰক্ষিত"],
    stay: "সুৰক্ষিত হ'লে য'ত আছে তাতে থাকক। এই পৃষ্ঠাটো প্ৰতি ৫ ছেকেণ্ডত আপডেট হয়।",
    another: "আন এটা SOS পঠিয়াওক",
    share: "🔗 পৰিয়ালৰ সৈতে শ্বেয়াৰ কৰক",
    share_note: "কেৱল এই লিংক থকা লোকেহে আপোনাৰ অৱস্থা চাব পাৰিব:",
    safe_at: "সুৰক্ষিতভাৱে পালেগৈ:",
    shelter: "আশ্ৰয় শিবিৰ",
    sms: "✉️ SMS যোগে পঠিয়াওক (ইণ্টাৰনেট নাই)",
    sms_note: "আপোনাৰ SMS এপটো উদ্ধাৰ নম্বৰলৈ এটা চুটি বাৰ্তাৰে খুলিব। সাধাৰণ SMS মাচুল লাগিব পাৰে।",
    safe_title: "মই সুৰক্ষিত নে?",
    safe_locate: "📍 মোৰ অৱস্থান ব্যৱহাৰ কৰক",
    nearest_shelter: "আটাইতকৈ ওচৰৰ খোলা আশ্ৰয় শিবিৰ (ঠাই আছে)",
    nearest_hospital: "আটাইতকৈ ওচৰৰ চিকিৎসালয় (OpenStreetMap)",
    roads_near: "আপোনাৰ ওচৰৰ পথ",
    no_shelter: "এতিয়া কোনো খোলা আশ্ৰয় শিবিৰত ঠাই নাই।",
  },
};

const KEY = "aq_phone_lang";

export function makeT(lang) {
  const d = DICT[lang] || DICT.en;
  return (key, vars) => {
    let s = d[key] ?? DICT.en[key] ?? key;
    if (typeof s === "string" && vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
    return s;
  };
}

/** Language of the phone pages, remembered on this phone (try/catch: private mode). */
export function usePhoneLang() {
  const [lang, setLangState] = useState(() => {
    try {
      const v = window.localStorage.getItem(KEY);
      return v && DICT[v] ? v : "en";
    } catch {
      return "en";
    }
  });
  useEffect(() => {
    try {
      document.documentElement.setAttribute("lang", lang);
    } catch {
      /* no document (tests) */
    }
  }, [lang]);
  const setLang = useCallback((v) => {
    setLangState(v);
    try {
      window.localStorage.setItem(KEY, v);
    } catch {
      /* private mode: only this visit */
    }
  }, []);
  return [lang, setLang, makeT(lang)];
}

// ---- SMS fallback ------------------------------------------------------------------
// Format (parsed by backend/services/sms_parse.py — keep both in step):
//   SOS <lat>,<lon> P<people> W<water code> [M<medical code>] <name>
const WATER_SHORT = { "ankle-deep": "ANKLE", "knee-deep": "KNEE", "waist-deep": "WAIST", "chest-deep": "CHEST", "water rising fast": "RISING" };

export function smsText({ lat, lon, people, water, medical, name }) {
  const w = WATER_SHORT[water] || "KNEE";
  const m = medical && medical !== "none" ? ` M${medical.toUpperCase()}` : "";
  const clean = String(name || "").replace(/\s+/g, " ").trim().slice(0, 40);
  return `SOS ${Number(lat).toFixed(5)},${Number(lon).toFixed(5)} P${people} W${w}${m} ${clean}`;
}

/** The rescue SMS number comes ONLY from configuration (VITE_SOS_SMS_NUMBER); none → no button. */
export function smsNumber() {
  try {
    const v = import.meta.env?.VITE_SOS_SMS_NUMBER;
    return v && String(v).trim() ? String(v).trim() : null;
  } catch {
    return null;
  }
}

export function smsHref(number, text) {
  return `sms:${number}?body=${encodeURIComponent(text)}`;
}
