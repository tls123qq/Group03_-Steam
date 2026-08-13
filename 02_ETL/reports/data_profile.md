# Data Profiling Report

ตรวจก่อนเข้าขั้น Clean — ขั้นนี้ไม่แก้ไขข้อมูลใด ๆ

| แหล่งข้อมูล | ประเภทปัญหา | รายละเอียด | จำนวน |
|---|---|---|---|
| store | Duplicate | steam_appid ซ้ำ | 0 |
| store | Missing | คอลัมน์ categories ว่าง | 403 |
| store | Missing | คอลัมน์ genres ว่าง | 373 |
| store | Missing | คอลัมน์ supported_languages ว่าง | 371 |
| store | Missing | คอลัมน์ publishers ว่าง | 445 |
| store | Missing | คอลัมน์ developers ว่าง | 27 |
| store | Missing | คอลัมน์ name ว่าง | 1 |
| store | Missing | ไม่มี price_overview | 5,701 |
| store | Missing | เกมฟรีที่ไม่มี price_overview (ปกติ ห้ามลบ) | 4,568 |
| store | Date | release_date เป็น dict ต้องแตกออกก่อน | 23,063 |
| store | Date | วันที่แปลงไม่ได้ เช่น Coming Soon | 0 |
| store | Format | supported_languages มี HTML ปน | 11,342 |
| store | Unit | ราคาเป็นหน่วยสตางค์ ต้องหาร 100 | 17,362 |
| store | Nested | คอลัมน์ platforms เป็น dict ซ้อน | 23,063 |
| store | Nested | คอลัมน์ achievements เป็น dict ซ้อน | 12,478 |
| store | Nested | คอลัมน์ recommendations เป็น dict ซ้อน | 7,294 |
| store | Nested | คอลัมน์ price_overview เป็น dict ซ้อน | 17,362 |
| review | Schema | รูปแบบคีย์ที่ต่างกันระหว่างแถว | 1 |
| review | Duplicate | steam_appid ซ้ำ | 0 |
| review | Missing | ค่าว่างทั้งไฟล์ | 0 |
| review | Invalid | positive + negative != total | 0 |
| review | Invalid | review_score นอกช่วง 0-9 | 0 |
| review | Invalid | ค่าติดลบ | 0 |
| review | ZeroVariance | คอลัมน์ที่มีค่าเดียวทั้งไฟล์ ['num_reviews'] | 1 |
| steamspy | Format | คอลัมน์ index ติดมาจากการ export ['Unnamed: 0'] | 1 |
| steamspy | Duplicate | appid ซ้ำ | 3,652 |
| steamspy | Missing | คอลัมน์ name ว่าง | 14 |
| steamspy | Missing | คอลัมน์ developer ว่าง | 302 |
| steamspy | Missing | คอลัมน์ publisher ว่าง | 567 |
| steamspy | Missing | คอลัมน์ score_rank ว่าง | 86,495 |
| steamspy | Missing | คอลัมน์ price ว่าง | 28 |
| steamspy | Missing | คอลัมน์ initialprice ว่าง | 21 |
| steamspy | Missing | คอลัมน์ discount ว่าง | 21 |
| steamspy | Unit | owners เป็นข้อความช่วง ต้องแปลงเป็นตัวเลข | 86,543 |
| steamspy | Invalid | ค่าที่แปลงเป็นตัวเลขไม่ได้ | 0 |
| steamspy | Invalid | ค่าติดลบในคอลัมน์ที่ไม่ควรติดลบ | 0 |
| steamspy | ZeroVariance | คอลัมน์ที่มีค่าเดียวทั้งไฟล์ [] | 0 |
| all | MismatchedKeys | คีย์คนละชื่อ (steam_appid vs appid) ต้อง rename ก่อน join | 1 |
| all | MismatchedKeys | มีใน store (steam_appid) แต่ไม่ครบแหล่งอื่น | 7,256 |
| all | MismatchedKeys | มีใน review (steam_appid) แต่ไม่ครบแหล่งอื่น | 7,256 |
| all | MismatchedKeys | มีใน steamspy (appid) แต่ไม่ครบแหล่งอื่น | 67,084 |