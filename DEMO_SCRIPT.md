# Demo narration script (about 3 minutes)

Read each block while the matching thing is on screen. Pause where it says.

---

**[0:00 – Landing on Maruti timeline]**
"This is Management Radar. It takes everything a company and its management
say in public, exchange filings and TV interviews, and puts it in one place.
Here's Maruti Suzuki. Each card is one disclosure, newest first. The headline,
the summary and the tags are written by the model from the document itself.
The grey 'Listed as' line is the title we were given, so you can see when the
content differs from the label."

**[0:30 – Scrolling the timeline]**
"Filings are red, interviews are navy. The August sales filing, the Q1
results, the e-Vitara launch, and the Chairman's interview with its duration."

**[0:45 – Promise tracker tab]**
"The promise tracker pulls out forward-looking statements only, with the
verbatim quote and where it came from. They're grouped by topic, so a filing
promise sits next to an interview promise on the same subject. That's the
consistency check: does management say the same thing on TV as in the
filing?"

**[1:10 – Chat: expansion question]**
"Now the chat. 'What has management said about expansion plans?' Every answer
is built only from passages retrieved from the database, and every sentence
carries a citation."
(pause while it answers)
"Two citations, both to the Chairman's interview. Clicking one opens the video
at that exact timestamp."

**[1:50 – Chat: trap question]**
"The important part is what it does when the answer isn't there. 'What did
Maruti say about its plans to build cars in Brazil?'"
(pause)
"Amber badge: not found in sources, no citations. It doesn't guess."

**[2:15 – Switch to Infosys, CEO question]**
"Same thing for Infosys. 'Who is the new CEO designate and when does Salil
Parekh step down?'"
(pause)
"Grounded, with a page citation into the earnings-call transcript that was
filed with the exchange. Clicking it opens the cached PDF on that page."

**[2:50 – Close]**
"Everything is in one SQLite file: companies, sources, chunks with page or
timestamp, AI outputs, claims, and a log of every question asked. Python,
FastAPI, Gemini on the free tier. Thanks."
