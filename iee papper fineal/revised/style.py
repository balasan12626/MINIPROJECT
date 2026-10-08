import re,sys,statistics as st,subprocess
txt=subprocess.run(["pdftotext","-enc","UTF-8",sys.argv[1],"-"],capture_output=True,text=True,encoding="utf-8").stdout
body=txt.split("REFERENCES")[0] if "REFERENCES" in txt else txt.split("References")[0]
body=re.sub(r"-\n","",body); body=re.sub(r"\s+"," ",body)
tells=["delve","crucial","furthermore","moreover","additionally","notably","leverag","seamless","robust","pivotal","landscape","realm","comprehensive","intricate","underscore","holistic","paramount","cutting-edge","in conclusion","it is important","plays a vital","not only","harness","foster","tapestry","navigat","ensure","facilitat","utiliz","novel","significant"]
low=body.lower()
hits={w:low.count(w) for w in tells if low.count(w)}
sents=[s for s in re.split(r"(?<=[.!?])\s+",body) if len(s.split())>3]
L=[len(s.split()) for s in sents]
print("words",len(body.split()),"sentences",len(L))
print("sent len mean %.1f sd %.1f min %d max %d"%(st.mean(L),st.pstdev(L),min(L),max(L)))
print("burstiness (sd/mean) %.2f"%(st.pstdev(L)/st.mean(L)))
print("em/en dashes",body.count("—")+body.count(" – "))
print("tell words",hits)
starts=[s.split()[0] for s in sents]; from collections import Counter; print("top openers",Counter(starts).most_common(6))
