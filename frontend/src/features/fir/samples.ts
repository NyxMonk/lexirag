/**
 * SYNTHETIC FIR samples for demonstration. Names, places and case details are invented;
 * they are not real FIRs and must not be presented as such.
 */
export interface FirSample {
  id: string;
  label: string;
  lang: string;
  text: string;
}

export const FIR_SAMPLES: FirSample[] = [
  {
    id: "en-ipc",
    label: "English · IPC (2023)",
    lang: "en",
    text: [
      "FIRST INFORMATION REPORT (SYNTHETIC SAMPLE)",
      "Police Station: Example Nagar, District Sample",
      "Date and time of report: 15/03/2023 11:20",
      "Date of occurrence: 13/03/2023",
      "Acts and sections: u/s 498A/406/34 IPC",
      "Brief facts: The informant states that after her marriage her husband and his parents repeatedly demanded money,",
      "kept her jewellery and refused to return it, and harassed her when she objected.",
    ].join("\n"),
  },
  {
    id: "hi-bns",
    label: "हिन्दी · BNS (2024)",
    lang: "hi",
    text: [
      "प्रथम सूचना रिपोर्ट (कृत्रिम नमूना)",
      "थाना: उदाहरण नगर, ज़िला नमूना",
      "सूचना दर्ज करने की तारीख: २२/०९/२०२४",
      "घटना की तारीख: २०/०९/२०२४",
      "अधिनियम एवं धाराएँ: भारतीय न्याय संहिता, 2023 की धारा 303(2), 317(2), 3(5)",
      "संक्षिप्त विवरण: शिकायतकर्ता के अनुसार दो व्यक्तियों ने बाज़ार से उसकी मोटरसाइकिल चुरा ली,",
      "जो बाद में एक अन्य व्यक्ति के पास से बरामद हुई।",
    ].join("\n"),
  },
  {
    id: "mr-ipc",
    label: "मराठी · IPC (2023)",
    lang: "mr",
    text: [
      "प्रथम खबर अहवाल (कृत्रिम नमुना)",
      "पोलीस ठाणे: उदाहरण पेठ",
      "खबर नोंद तारीख: 08/11/2023",
      "घटनेची तारीख: 07/11/2023",
      "कलम: भादंवि कलम 323, 504, 506, 34",
      "थोडक्यात हकीकत: फिर्यादी यांच्या शेजाऱ्यांनी पाण्याच्या वादातून त्यांना शिवीगाळ करून मारहाण केली",
      "व जीवे मारण्याची धमकी दिली.",
    ].join("\n"),
  },
];
