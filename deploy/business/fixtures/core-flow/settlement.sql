-- Synthetic settlement fixture base table, derived from mock结算信息数据库.docx.
-- 54 original definitions / 50 distinct source fields, plus SYSTEM_ID requested on 2026-10-13.
-- UPDATE_TIME is the agreed settlement time.
-- Workflow convention: quantities in sets; compare CNT * PRIC with independent count * PRIC.
-- User requested one table: each row is one detail with its settlement header fields.
CREATE TABLE IF NOT EXISTS public.core_flow_settlement_v1 (
    "ORGAN_CODE" TEXT CHECK (char_length("ORGAN_CODE") <= 18) NOT NULL,
    "ORGAN_NAME" TEXT CHECK (char_length("ORGAN_NAME") <= 80) NOT NULL,
    "ORGAN_ADMDVS" TEXT CHECK (char_length("ORGAN_ADMDVS") <= 6) NOT NULL,
    "ORGAN_LV" TEXT CHECK (char_length("ORGAN_LV") <= 6) NOT NULL,
    "FIX_ORGAN_CODE" TEXT CHECK (char_length("FIX_ORGAN_CODE") <= 12) NOT NULL,
    "FIX_ORGAN_NAME" TEXT CHECK (char_length("FIX_ORGAN_NAME") <= 80) NOT NULL,
    "DATA_SOURCE" TEXT CHECK (char_length("DATA_SOURCE") <= 16) NOT NULL,
    "SYSTEM_ID" VARCHAR(16) NOT NULL,
    "SETL_HOS_ID" TEXT CHECK (char_length("SETL_HOS_ID") <= 80) NOT NULL,
    "INIT_SETL_HOS_ID" TEXT CHECK (char_length("INIT_SETL_HOS_ID") <= 80),
    "SETL_MED_ID" TEXT CHECK (char_length("SETL_MED_ID") <= 80),
    "INIT_SETL_MED_ID" TEXT CHECK (char_length("INIT_SETL_MED_ID") <= 80),
    "MDTRT_SN" TEXT CHECK (char_length("MDTRT_SN") <= 100) NOT NULL,
    "MDTRT_ID" TEXT CHECK (char_length("MDTRT_ID") <= 30),
    "MED_PAY_FLAG" TEXT CHECK (char_length("MED_PAY_FLAG") <= 2) NOT NULL,
    "PSN_NO" TEXT CHECK (char_length("PSN_NO") <= 64),
    "PSN_NAME" TEXT CHECK (char_length("PSN_NAME") <= 40) NOT NULL,
    "PSN_CERT_TYPE" TEXT CHECK (char_length("PSN_CERT_TYPE") <= 2) NOT NULL,
    "CERTNO" TEXT CHECK (char_length("CERTNO") <= 24) NOT NULL,
    "SOC_SEC_CARD_NO" TEXT CHECK (char_length("SOC_SEC_CARD_NO") <= 36),
    "GEND" TEXT CHECK (char_length("GEND") <= 1) NOT NULL,
    "OP_EM_MARK" TEXT CHECK (char_length("OP_EM_MARK") <= 12) NOT NULL,
    "OP_EM_NO" TEXT CHECK (char_length("OP_EM_NO") <= 36) NOT NULL,
    "RCD_DT" TEXT CHECK (char_length("RCD_DT") <= 15) NOT NULL,
    "REFD_SETL_FLAG" NUMERIC(1,0) NOT NULL,
    "MED_TYPE" TEXT CHECK (char_length("MED_TYPE") <= 12),
    "MEDFEE_SUMAMT" NUMERIC(16,2) NOT NULL,
    "FUND_PAY_SUMAMT" NUMERIC(16,2),
    "PSN_PART_AMT" NUMERIC(16,2),
    "ACCT_PAY" NUMERIC(16,2),
    "PSN_CASH_PAY" NUMERIC(16,2),
    "HOSP_PART_AMT" NUMERIC(16,2),
    "UPDATE_TIME" TIMESTAMPTZ NOT NULL,
    "SETL_FEE_LIST_ID" TEXT CHECK (char_length("SETL_FEE_LIST_ID") <= 80) NOT NULL,
    "RPT_NO" TEXT CHECK (char_length("RPT_NO") <= 512),
    "FEEDETL_SN" TEXT CHECK (char_length("FEEDETL_SN") <= 36) NOT NULL,
    "INIT_FEEDETL_SN" TEXT CHECK (char_length("INIT_FEEDETL_SN") <= 80),
    "HOS_PROJ_NO" TEXT CHECK (char_length("HOS_PROJ_NO") <= 200) NOT NULL,
    "HOS_PROJ_NAME" TEXT CHECK (char_length("HOS_PROJ_NAME") <= 1000) NOT NULL,
    "HILIST_CODE" TEXT CHECK (char_length("HILIST_CODE") <= 36),
    "HILIST_NAME" TEXT CHECK (char_length("HILIST_NAME") <= 36),
    "LIST_TYPE" TEXT CHECK (char_length("LIST_TYPE") <= 36),
    "MED_LIST_CODG" TEXT CHECK (char_length("MED_LIST_CODG") <= 36),
    "MEDINS_LIST_CODG" TEXT CHECK (char_length("MEDINS_LIST_CODG") <= 36) NOT NULL,
    "MEDINS_LIST_NAME" TEXT CHECK (char_length("MEDINS_LIST_NAME") <= 36) NOT NULL,
    "MED_CHRGITM_TYPE" TEXT CHECK (char_length("MED_CHRGITM_TYPE") <= 36),
    "PRODNAME" TEXT CHECK (char_length("PRODNAME") <= 36),
    "SPEC" TEXT CHECK (char_length("SPEC") <= 36),
    "DOSFORM_NAME" TEXT CHECK (char_length("DOSFORM_NAME") <= 36),
    "CNT" NUMERIC(10,2) NOT NULL,
    "PRIC" NUMERIC(10,2) NOT NULL,
    PRIMARY KEY ("ORGAN_CODE", "DATA_SOURCE", "SETL_FEE_LIST_ID")
);
COMMENT ON TABLE public.core_flow_settlement_v1 IS 'Synthetic fixture; 50 original fields plus inspection SYSTEM_ID; settlement time UPDATE_TIME; quantities in sets; compare CNT * PRIC with independent count * PRIC.';
COMMENT ON COLUMN public.core_flow_settlement_v1."ORGAN_CODE" IS '采集医疗机构代码；对接的医疗机构代码，采用18位“统一社会信用代码”；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."ORGAN_NAME" IS '采集医疗机构名称；医疗机构第一执业许可名称；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."ORGAN_ADMDVS" IS '医疗机构医保区划；医疗机构所属医保区划；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."ORGAN_LV" IS '医疗机构等级；医疗机构等级；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."FIX_ORGAN_CODE" IS '定点医药机构编号；医疗机构医保定点编号，采用12位的H码；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."FIX_ORGAN_NAME" IS '定点医药机构名称；定点医药机构名称；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."DATA_SOURCE" IS '信息系统院内唯一ID；信息系统在医疗机构的唯一ID，该字段用来解决同一家医疗机构有多个系统，造成部分ID重复问题，建议从HIS01开始。；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."SYSTEM_ID" IS '检查所属系统的院内唯一ID；最大16字符；用户2026-10-13补充；不替代DATA_SOURCE';
COMMENT ON COLUMN public.core_flow_settlement_v1."SETL_HOS_ID" IS '院内结算id；主键，院内结算唯一号；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."INIT_SETL_HOS_ID" IS '原院内结算id；原院内结算id，退费时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."SETL_MED_ID" IS '医保结算id；医保结算id，医保结算时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."INIT_SETL_MED_ID" IS '原医保结算id；原医保结算id，医保退费时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."MDTRT_SN" IS '就医流水号；机构内生成唯一就诊流水号；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."MDTRT_ID" IS '就诊id；医保病人必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."MED_PAY_FLAG" IS '医保结算标识；是否医保结算，0：否，1：是；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."PSN_NO" IS '患者人员编号；医保患者必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."PSN_NAME" IS '患者姓名；居民本人正式登记注册的姓名；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."PSN_CERT_TYPE" IS '患者证件类型；详见“RC038-国家公立医院绩效考核患者证件类别”码表（表5）；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."CERTNO" IS '患者证件号码；卡证号码应与卡证类型相匹配；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."SOC_SEC_CARD_NO" IS '社会保障卡卡号；就诊时的社会保障卡卡号（社会保障卡就诊时必填）；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."GEND" IS '性别代码；0、未知的性别，1、男性，2、女性，9、未说明的性别；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."OP_EM_MARK" IS '门诊/急诊/住院/体检标识；1、普通门诊、2急诊，3、住院，4、体检；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."OP_EM_NO" IS '门诊/急诊/住院/体检编号；同门诊/急诊/住院/体检关联；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."RCD_DT" IS '收费/退费日期时间；收费/退费日期时间；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."REFD_SETL_FLAG" IS '退费结算标志；收费或退费的标志，0、正常；1、退费；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."MED_TYPE" IS '医疗类别；详见附录表13，医保结算时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."MEDFEE_SUMAMT" IS '医疗费总额；医疗费总额，医保结算时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."FUND_PAY_SUMAMT" IS '基金支付总额；基金支付总额，医保结算时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."PSN_PART_AMT" IS '个人负担总金额；个人负担总金额，医保结算时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."ACCT_PAY" IS '个人账户支出；个人账户支出，医保结算时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."PSN_CASH_PAY" IS '个人现金支出；个人现金支出，医保结算时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."HOSP_PART_AMT" IS '医院负担金额；医院负担金额，医保结算时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."UPDATE_TIME" IS '最终结算时间；最终结算时间（精确到秒），采集按照该字段定时采集；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."SETL_FEE_LIST_ID" IS '结算明细id；主键，院内结算明细id；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."RPT_NO" IS '申请单编号；院内申请单编号，检查检验必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."FEEDETL_SN" IS '费用明细流水号；费用明细流水号；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."INIT_FEEDETL_SN" IS '原费用明细流水号；原费用明细流水号，退费时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."HOS_PROJ_NO" IS '院内项目编码；该项目在医疗机构中的编码；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."HOS_PROJ_NAME" IS '院内项目名称；该项目在医疗机构中的名称；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."HILIST_CODE" IS '医保目录编码；医保服务项目价格目录编码，医保结算时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."HILIST_NAME" IS '医保目录名称；医保服务项目价格目录名称，医保结算时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."LIST_TYPE" IS '目录类别；101西药中成药，102中药饮片，103自制剂，104民族药，201医疗服务项目，301医用耗材；医保结算时必填；来源：mock结算信息数据库.docx及用户补充码表';
COMMENT ON COLUMN public.core_flow_settlement_v1."MED_LIST_CODG" IS '医疗目录编码；药剂或者耗材的医疗目录编码，医保结算时必填；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."MEDINS_LIST_CODG" IS '医药机构目录编码；院内收费目录编码 ；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."MEDINS_LIST_NAME" IS '医药机构目录名称；院内收费目录名称；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."MED_CHRGITM_TYPE" IS '医疗收费项目类别；详见附录表16；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."PRODNAME" IS '商品名；商品名；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."SPEC" IS '规格；规格；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."DOSFORM_NAME" IS '剂型名称；剂型名称；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."CNT" IS '项目数量；项目数量；来源：mock结算信息数据库.docx';
COMMENT ON COLUMN public.core_flow_settlement_v1."PRIC" IS '项目单价（元）；项目单价（元）；来源：mock结算信息数据库.docx';
