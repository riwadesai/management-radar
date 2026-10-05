# Demo narration script

The recording is `demo/demo.mp4` (2 min 12 s, no audio). Timestamps below are
the actual moments in that video (`demo/marks.txt`). Play it and read each
block when its scene appears. Regenerate the video any time with
`python scripts/record_demo.py` while the app is running.

---

**[0:00 – Maruti timeline]**
"This is Management Radar. It takes everything a company and its management
say in public, exchange filings and TV interviews, and puts it in one place.
Here's Maruti Suzuki. Each card is one disclosure, newest first. The headline,
the summary and the tags are written by the model from the document itself.
The grey 'Listed as' line is the title we were given, so you can see when the
content differs from the label."

**[0:22 – Scrolling the timeline]**
"Filings are red, interviews are navy. August sales, Q1 results, the Q4
presentation, the Chairman's interview with its length, and the e-Vitara
launch."

**[0:36 – Promise tracker]**
"The promise tracker pulls out forward-looking statements only: the promise,
the verbatim quote, and where it was said. They're grouped by topic so a
filing promise sits next to an interview promise on the same subject. That's
the consistency check: does management say the same thing on TV as in the
filing?"

**[1:01 – Chat: expansion question]**
"Now the chat. 'What has management said about expansion plans?' The system
first pulls the best passages out of the database, then the model answers
only from those, with a citation on every sentence."

**[1:05 – Answer appears]**
"Grounded: one production line each at Kharkhoda and Hansalpur, about two
hundred and fifty thousand extra cars. The citation is the Chairman's
interview at five minutes fifty-six. Clicking it opens the video at that
second."

**[1:21 – Chat: trap question]**
"What matters more is what it does when the answer isn't there. 'What did
Maruti say about its plans to build cars in Brazil?'"

**[1:26 – Not found]**
"Amber badge, not found in sources, no citations. It doesn't guess."

**[1:38 – Infosys]**
"Same for Infosys. 'Who is the new CEO designate and when does Salil Parekh
step down?'"

**[1:46 – CEO answer]**
"Ashiss Dash, from April 1st 2027, cited to page 4 of the earnings-call
transcript that was filed with the exchange. Clicking opens the cached PDF on
that page."

**[2:02 – Close]**
"Everything lives in one SQLite file: companies, sources, chunks with a page
or timestamp, AI outputs, claims, and a log of every question asked. Python,
FastAPI, Gemini on the free tier. Thanks."
