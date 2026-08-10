from __future__ import annotations

import json
from typing import Any

CAUSES: dict[str, dict[str, Any]] = {
    "private_lending": {
        "label": "民间借贷纠纷",
        "cause_code": "private_lending",
        "template": "起诉状/要素式民间借贷纠纷起诉状.docx",
        "schema": "private_lending_complaint.v1.json",
        "aliases": ["民间借贷纠纷", "民间借贷"],
        "keywords": ["借条", "欠条", "借款", "出借", "还款", "本金", "利息", "借款人"],
        "issues": ["民间借贷关系成立与借款实际交付", "借款到期、还款及剩余本金", "借款利息及逾期利息"],
    },
    "sales_contract": {
        "label": "买卖合同纠纷",
        "cause_code": "sales_contract",
        "template": "起诉状/要素式买卖合同纠纷起诉状.docx",
        "schema": "sales_contract_complaint.v1.json",
        "aliases": ["买卖合同纠纷"],
        "keywords": ["买卖合同", "买方", "卖方", "货款", "供货", "交货", "订单", "送货单", "对账单", "发票", "验收"],
        "issues": ["买卖合同关系成立及合同效力", "标的物交付、验收与价款支付", "迟延履行、违约金及损失"],
    },
    "labor_dispute": {
        "label": "劳动争议",
        "cause_code": "labor_dispute",
        "template": "起诉状/要素式劳动争议起诉状.docx",
        "schema": "labor_dispute_complaint.v1.json",
        "aliases": ["劳动争议", "劳动纠纷"],
        "keywords": ["劳动合同", "工资", "用人单位", "入职", "离职", "解除劳动", "社会保险", "社保", "劳动仲裁", "加班费"],
        "issues": ["劳动关系成立及劳动合同履行", "工资、加班费、社会保险及经济补偿", "劳动关系解除与仲裁前置程序"],
    },
    "divorce": {
        "label": "离婚纠纷",
        "cause_code": "divorce",
        "template": "起诉状/要素式离婚纠纷起诉状.docx",
        "schema": "divorce_complaint.v1.json",
        "aliases": ["离婚纠纷"],
        "keywords": ["离婚", "夫妻感情", "共同财产", "共同债务", "子女抚养", "抚养费", "探望权", "结婚"],
        "issues": ["婚姻关系及感情确已破裂", "夫妻共同财产与共同债务分割", "子女抚养、抚养费与探望权"],
    },
    "traffic_accident": {
        "label": "机动车交通事故责任纠纷",
        "cause_code": "traffic_accident",
        "template": "起诉状/要素式机动车交通事故责任纠纷起诉状.docx",
        "schema": "traffic_accident_complaint.v1.json",
        "aliases": ["机动车交通事故责任纠纷", "交通事故责任纠纷"],
        "keywords": ["交通事故", "责任认定", "机动车", "医疗费", "误工费", "护理费", "残疾赔偿金", "交强险", "财产损失"],
        "issues": ["交通事故发生经过与责任认定", "人身损害各项赔偿（医疗费、误工费、护理费、残疾赔偿金等）", "机动车投保情况及财产损失"],
    },
    "work_injury_insurance": {
        "label": "工伤保险资格或者待遇认定",
        "cause_code": "work_injury_insurance",
        "template": "起诉状/要素式工伤保险资格或者待遇认定起诉状.docx",
        "schema": "work_injury_complaint.v1.json",
        "aliases": [
            "工伤保险资格或者待遇认定",
            "工伤保险资格或待遇认定",
        ],
        "keywords": ["工伤", "工伤认定", "不予认定工伤", "工伤保险", "职业病", "劳动能力鉴定", "人社局", "行政复议"],
        "issues": ["职工与用人单位是否存在劳动关系", "事故伤害或职业病发生及工伤认定决定", "工伤决定的违法之处与救济途径"],
    },
    "house_sale": {
        "label": "房屋买卖合同纠纷",
        "cause_code": "house_sale",
        "template": "起诉状/要素式房屋买卖合同纠纷起诉状.docx",
        "schema": "house_sale_complaint.v1.json",
        "aliases": ["房屋买卖合同纠纷", "商品房买卖合同纠纷"],
        "keywords": ["房屋买卖", "购房款", "商品房", "首付款", "定金", "交房", "不动产登记", "房产证", "中介服务费"],
        "issues": ["房屋买卖合同关系成立与效力", "购房款支付、房屋交付与登记", "违约责任与质量损害赔偿"],
    },
    "house_lease": {
        "label": "房屋租赁合同纠纷",
        "cause_code": "house_lease",
        "template": "起诉状/要素式房屋租赁合同纠纷起诉状.docx",
        "schema": "house_lease_complaint.v1.json",
        "aliases": ["房屋租赁合同纠纷"],
        "keywords": ["房屋租赁", "租赁合同", "出租人", "承租人", "租金", "押金", "租赁期限", "占有使用费", "转租"],
        "issues": ["租赁合同成立与租赁期限、租金约定", "租金支付与逾期、押金返还", "合同解除与租赁物返还、占有使用费"],
    },
    "trademark_infringement": {
        "label": "侵害商标权纠纷",
        "cause_code": "trademark_infringement",
        "template": "起诉状/要素式侵害商标权纠纷起诉状.docx",
        "schema": "trademark_infringement_complaint.v1.json",
        "aliases": [
            "侵害商标权纠纷",
            "侵犯商标权纠纷",
            "侵犯商标专用权纠纷",
            "商标权侵权纠纷",
            "商标侵权纠纷",
            "商标侵权",
        ],
        "keywords": [
            "商标注册证", "注册商标", "商标号", "核定商品", "核定服务",
            "侵权标识", "近似商标", "销售侵权商品", "商标许可", "驰名商标",
        ],
        "issues": [
            "原告主体资格及注册商标权利状态",
            "被诉标识与核定商品或服务是否构成商标侵权",
            "停止侵权、损害赔偿、惩罚性赔偿及合理开支",
        ],
    },
    "invention_patent_infringement": {
        "label": "侵害发明专利权纠纷",
        "cause_code": "invention_patent_infringement",
        "template": "起诉状/要素式侵害发明专利权纠纷起诉状.docx",
        "schema": "invention_patent_infringement_complaint.v1.json",
        "aliases": [
            "侵害发明专利权纠纷",
            "侵犯发明专利权纠纷",
            "发明专利权侵权纠纷",
            "发明专利侵权纠纷",
            "发明专利侵权",
        ],
        "keywords": [
            "发明专利", "专利号", "权利要求", "说明书", "被诉侵权产品",
            "技术特征", "全面覆盖原则", "等同特征", "无效宣告", "专利实施许可",
        ],
        "issues": [
            "原告主体资格、专利权利状态及权利要求保护范围",
            "被诉侵权产品技术特征是否落入涉案权利要求保护范围",
            "侵权行为、损害赔偿、惩罚性赔偿及合理开支",
            "专利确权行政程序及关联民事案件",
        ],
    },
}

COMMON_DOCUMENT_FIELDS = [
    "document.claims", "document.facts_and_reasons", "document.evidence_list",
]
# Backward-compatible export. Party fields intentionally live in
# drafting_lite.party_extraction and are never derived from a cause config.
COMMON_FIELDS = COMMON_DOCUMENT_FIELDS

UNSUPPORTED_DOMAIN_KEYWORDS = {
    "保险或车辆保障服务争议": [
        "保险合同", "保险公司", "保单", "车险", "投保", "被保险人", "理赔",
        "不计免赔", "机动车损失险", "第三者责任险",
    ],
}

CAUSE_FIELDS = {
    "private_lending": [
        "claims.principal.amount", "claims.interest.amount", "claims.interest.calculation",
        "claims.enforcement_costs", "claims.total_amount", "jurisdiction.agreement",
        "loan.contract.summary", "loan.principal.agreed", "loan.principal.delivered",
        "loan.delivery.method", "loan.term", "loan.interest.rate", "loan.delivery.items",
        "loan.repayment.summary", "loan.default.summary", "guarantee.summary",
    ],
    "sales_contract": [
        "sales.contract.summary", "sales.seller", "sales.buyer", "sales.goods.summary",
        "sales.price_payment", "sales.delivery_terms", "sales.quality_terms",
        "sales.performance.summary", "sales.default.summary", "sales.demand.summary",
        "claims.price.amount", "claims.interest_penalty", "claims.loss.amount",
        "claims.contract_relief", "claims.total_amount", "jurisdiction.agreement",
    ],
    "labor_dispute": [
        "labor.contract.summary", "labor.performance.summary", "labor.termination.summary",
        "labor.injury.summary", "labor.arbitration.summary", "claims.wages",
        "claims.double_wages", "claims.overtime", "claims.annual_leave",
        "claims.social_insurance_loss", "claims.compensation", "claims.illegal_termination",
        "claims.total_amount",
    ],
    "divorce": [
        "divorce.dissolution", "divorce.community_property", "divorce.community_debt",
        "divorce.child_custody", "divorce.child_support", "divorce.visitation",
        "divorce.compensation", "claims.other", "claims.total_amount",
        "divorce.marriage.summary", "divorce.property.summary", "divorce.debt.summary",
        "divorce.custody.summary", "divorce.support.summary", "divorce.visitation.summary",
        "divorce.compensation.summary",
    ],
    "traffic_accident": [
        "claims.medical_expense", "claims.nursing_expense", "claims.nutrition_expense",
        "claims.hospitalization_meal_allowance", "claims.lost_wages", "claims.transportation_expense",
        "claims.disability_compensation", "claims.disability_aid_expense", "claims.death_compensation",
        "claims.mental_distress_solatium", "claims.property_loss", "claims.other",
        "claims.total_amount", "traffic.accident.summary", "traffic.liability.summary",
        "traffic.insurance.summary",
    ],
    "work_injury_insurance": [
        "work.revoke_recognition", "work.revoke_non_recognition", "claims.other",
        "work.labor_relation.summary", "work.prior_arbitration.summary", "work.position.summary",
        "work.injury_date.summary", "work.decision.summary", "work.receipt.summary",
        "work.illegality.summary", "work.prior_review.summary",
    ],
    "house_sale": [
        "house_sale.contract_relation", "house_sale.payment", "house_sale.delivery",
        "house_sale.registration", "house_sale.agency_fee", "house_sale.quality_damage",
        "house_sale.loan_discharge", "house_sale.appraisal_fee", "claims.other",
        "claims.total_amount", "jurisdiction.agreement",
        "house_sale.contract.summary", "house_sale.payment.summary", "house_sale.delivery.summary",
        "house_sale.registration.summary", "house_sale.agency_fee.summary", "house_sale.quality.summary",
    ],
    "house_lease": [
        "house_lease.rent", "house_lease.overdue_interest", "house_lease.delivery",
        "house_lease.rescission", "house_lease.return_and_compensation", "house_lease.occupation_fee",
        "house_lease.utility_fee", "house_lease.deposit_return", "claims.other",
        "claims.total_amount", "jurisdiction.agreement",
        "house_lease.contract.summary", "house_lease.parties.summary", "house_lease.subject.summary",
        "house_lease.term.summary", "house_lease.rent.summary", "house_lease.other_fee.summary",
        "house_lease.breach.summary", "house_lease.deposit.summary", "house_lease.rent_payment.summary",
        "house_lease.overdue.summary",
    ],
    "trademark_infringement": [
        "claims.stop_infringement", "claims.economic_loss", "claims.reasonable_expenses",
        "claims.litigation_costs", "claims.other", "claims.total_amount",
        "trademark.plaintiff_standing", "trademark.right_status",
        "trademark.registration_number", "trademark.approved_class",
        "trademark.validity_period", "trademark.license_status",
        "trademark.use_and_fame", "trademark.accused_mark",
        "trademark.accused_goods_services", "trademark.infringement",
        "trademark.infringement_period", "trademark.infringement_place",
        "trademark.intent_and_harm", "trademark.punitive_damages_basis",
        "trademark.related_cases", "trademark.right_basis_summary",
    ],
    "invention_patent_infringement": [
        "claims.stop_infringement", "claims.economic_loss", "claims.reasonable_expenses",
        "claims.joint_liability", "claims.delayed_performance_penalty",
        "claims.litigation_costs", "claims.other", "claims.total_amount",
        "jurisdiction.agreement", "patent.pre_litigation_preservation",
        "patent.foreign_related", "patent.hk_macao_taiwan_related",
        "patent.plaintiff_standing", "patent.number", "patent.name",
        "patent.field", "patent.application_date", "patent.priority_date",
        "patent.grant_date", "patent.asserted_claims", "patent.right_status",
        "patent.right_basis_summary",
        "patent.technical_comparison_summary", "patent.accused_product",
        "patent.infringement_acts", "patent.infringement_period",
        "patent.discovery", "patent.joint_infringement", "patent.other_facts",
        "patent.compensatory_damages_basis", "patent.punitive_damages_basis",
        "patent.reasonable_expenses_basis", "patent.joint_liability_basis",
        "patent.other_liability", "patent.related_proceedings",
        "patent.other_notes", "patent.independent_claim_features",
        "patent.dependent_claim_features", "patent.validity_proceedings",
        "patent.related_civil_cases",
    ],
}

AUTHORITY_KEYWORDS = {
    "private_lending": ["民间借贷", "借款合同", "出借人", "借款人", "返还借款"],
    "sales_contract": ["买卖合同", "出卖人", "买受人", "标的物交付", "支付价款"],
    "labor_dispute": ["劳动合同", "劳动者", "用人单位", "劳动报酬", "经济补偿"],
    "divorce": ["离婚", "夫妻感情确已破裂", "夫妻共同财产", "子女抚养", "探望"],
    "traffic_accident": ["交通事故", "人身损害赔偿", "机动车", "侵权责任", "残疾赔偿金"],
    "work_injury_insurance": ["工伤保险", "工伤认定", "职业病", "劳动能力鉴定", "行政诉讼法"],
    "house_sale": ["房屋买卖", "商品房", "不动产登记", "购房款", "违约责任"],
    "house_lease": ["房屋租赁", "出租人", "承租人", "租金", "租赁合同"],
    "trademark_infringement": [
        "注册商标专用权", "商标侵权", "相同或者近似商标",
        "混淆可能性", "侵权商品", "惩罚性赔偿",
    ],
    "invention_patent_infringement": [
        "发明专利权", "权利要求保护范围", "全面覆盖原则",
        "等同侵权", "被诉侵权产品", "无效宣告",
    ],
}


def _json_object(raw: str) -> dict[str, Any]:
    """从 LLM 输出中提取第一个完整 JSON 对象（含智能引号归一化）。

    共享 helper：material_agent 与 drafting_agent 都用它解析结构化输出。
    """
    def decode_first(text: str) -> dict[str, Any]:
        start = text.find("{")
        if start < 0:
            raise ValueError("JSON object not found")
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    value = json.loads(text[start : index + 1])
                    if not isinstance(value, dict):
                        raise ValueError("structured output must be object")
                    return value
        raise ValueError("incomplete JSON object")

    text = raw.strip()
    try:
        # Valid JSON may legitimately contain Chinese quotation marks inside a
        # string. Parse it unchanged first, otherwise replacing those marks
        # would introduce unescaped ASCII quotes and corrupt the JSON.
        return decode_first(text)
    except (ValueError, json.JSONDecodeError):
        normalized = text.replace("“", '"').replace("”", '"')
        if normalized == text:
            raise
        return decode_first(normalized)
