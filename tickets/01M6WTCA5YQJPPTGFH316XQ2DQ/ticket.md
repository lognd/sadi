+++
id = "01M6WTCA5YQJPPTGFH316XQ2DQ"
title = "Publish OpenAPI and generate TypeScript client into web/src/api"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T05:33:56Z"
updated = "2026-11-08T05:58:16Z"
scope = ["web/src/api/**", "python/sadi/server/openapi_export.py", "python/tests/server/test_openapi_export.py", "web/package.json", "web/src/api/schema.test.ts", "docs/web-api-client.md", "changelog.d/01M6W7R0KH8QFP4K9PTM197V9E.changed.md", "changelog.d/01M6W7R0PMCGFDSFY53XDK2EVN.changed.md", "changelog.d/01M6W7R0R9PGCDJWAD321F3H53.changed.md", "changelog.d/01M6W7R0VNQVPZ47CD080SB0TA.changed.md", "changelog.d/01M6W7R0XB2WMP03ZGW8XCPH41.changed.md", "changelog.d/01M6W7R0YWS8EXHXFBNZCE4AHC.added.md", "changelog.d/01M6W7R10HDC6A2K576Q4YBED4.changed.md", "changelog.d/01M6W7R121020FDM1SK2GGPZ5K.changed.md", "changelog.d/01M6W7R13KW0FFYHZJ7FY28A3R.changed.md", "changelog.d/01M6W7R155JD0XGVXHDSP19B1H.changed.md", "changelog.d/01M6W7R16PR162ZWC8EM7BT5SB.changed.md", "changelog.d/01M6W7R1883HHXY4XYEJA5DMTN.changed.md", "changelog.d/01M6W7R1BJ1PJWFD0FQSB1MWFD.changed.md", "changelog.d/01M6W7R1D3BVJZMCDT7CSWAMV8.changed.md", "changelog.d/01M6W7R1ENM05D2AQSTPVJNZ7V.changed.md", "changelog.d/01M6W7R1G903HZ7V7JRCYC6ZT7.added.md", "changelog.d/01M6W7R1HWQMSEX38TQM27Y4NY.changed.md", "changelog.d/01M6W7R1KH0MVS56MX07Q9BX19.changed.md", "changelog.d/01M6W7R1N7W6ZKBBM4M7NDJSG8.added.md", "changelog.d/01M6W7R1RD3P97HFFDZ2NVD83Y.changed.md", "changelog.d/01M6W7R1T397W3C0JZV66MX8BW.changed.md", "changelog.d/01M6W7R1VQHABR51SH64668M06.changed.md", "changelog.d/01M6W7R1XA74780R58PGCJAR1J.added.md", "changelog.d/01M6W7R1Z1E430ZNZ51V9NMTHC.added.md", "changelog.d/01M6W7R20Q20BHCEP78X42K86Y.changed.md", "changelog.d/01M6W7R226VMAMHYPDBQTAS277.added.md", "changelog.d/01M6W7R23Q44RD6WVCBGKVPN2E.changed.md", "changelog.d/01M6W7R257EXZX1RD7VT3M5GJG.changed.md", "changelog.d/01M6W7R28HX7237GMXSNQKWT3Y.changed.md", "changelog.d/01M6W7R2A727G6H66B6FBSDE1R.changed.md", "changelog.d/01M6W7R2BS0R89GW39HM0XPX0J.changed.md", "changelog.d/01M6W7R2DCY0H5XQ9F53F2W55E.changed.md", "changelog.d/01M6W7R2F3KJWQCWEKZK6BT3MG.changed.md", "changelog.d/01M6W7R2GTD88HAHEJ4VAX9DG6.changed.md", "changelog.d/01M6W7R2M88JFNKRESHJBD8YVD.changed.md", "changelog.d/01M6W7R2NWFTQBK7FRWGX511CP.changed.md", "changelog.d/01M6W7R2QFWW5VYSHCVA8Y67RG.changed.md", "changelog.d/01M6W7R2TPG1HC0F9QHDQ1C3W6.changed.md", "changelog.d/01M6W7R2XY9DB0PFREY9TZ8D2S.changed.md", "changelog.d/01M6W7R2ZMZSCRWKCRFHAH4MTB.changed.md", "changelog.d/01M6W7R31CM6MP54RXV36JQFXT.changed.md", "changelog.d/01M6W7R335N9GPFD4DYXP2D6HY.changed.md", "changelog.d/01M6W7R34VRSAYPG4SNQPQKQEK.changed.md", "changelog.d/01M6W7R36G6BYYB4RBC60ZNFTD.changed.md", "changelog.d/01M6W7R383ZG0WZNNVJMQYWW87.changed.md", "changelog.d/01M6W7R3BBDEXG9CPYWTQ7ZKZW.changed.md", "changelog.d/01M6W7R3D3KT3NM6JETDDAPA9P.changed.md", "changelog.d/01M6W7R3EPVRGG4R93B7WJVKMW.changed.md", "changelog.d/01M6W7R3G88NFY3N76MPX6X3ZQ.changed.md", "changelog.d/01M6W7R3J00J2HQ7XPW19WDD6Q.changed.md", "changelog.d/01M6W7R3KN3HXVMJQ1D3MJNBZY.added.md", "changelog.d/01M6W7R3N96SVM2D2GQQTA833F.added.md", "changelog.d/01M6W7R3Q5RVEC8YFA37P8582F.changed.md", "changelog.d/01M6W7R3RXWS1WSH3TPXMK16Q2.changed.md", "changelog.d/01M6W7R3TJETR6N3EVA9PMPWH8.changed.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R3XY1B0BF689RX3H80G2"

[[acceptance]]
text = "Publish OpenAPI and generate TypeScript client into web/src/api"
bound = false
+++

found while working ~X3H80G2 (split out of its original acceptance). Generated client must be drift-checked.
