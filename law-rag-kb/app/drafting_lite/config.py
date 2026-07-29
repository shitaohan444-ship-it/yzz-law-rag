from __future__ import annotations

import json
from typing import Any

CAUSES: dict[str, dict[str, Any]] = {
    "private_lending": {
        "label": "民间借贷纠纷",
        "cause_code": "private_lending",
        "template": "起诉状/要素式民间借贷纠纷起诉状.docx",
        "schema": "private_lending_complaint.v1.json",
        "keywords": ["借条", "欠条", "借款", "出借", "还款", "本金", "利息", "借款人"],
        "issues": ["民间借贷关系成立与借款实际交付", "借款到期、还款及剩余本金", "借款利息及逾期利息"],
    },
    "sales_contract": {
        "label": "买卖合同纠纷",
        "cause_code": "sales_contract",
        "template": "起诉状/要素式买卖合同纠纷起诉状.docx",
        "schema": "sales_contract_complaint.v1.json",
        "keywords": ["买卖合同", "买方", "卖方", "货款", "供货", "交货", "订单", "送货单", "对账单", "发票", "验收"],
        "issues": ["买卖合同关系成立及合同效力", "标的物交付、验收与价款支付", "迟延履行、违约金及损失"],
    },
    "labor_dispute": {
        "label": "劳动争议",
        "cause_code": "labor_dispute",
        "template": "起诉状/要素式劳动争议起诉状.docx",
        "schema": "labor_dispute_complaint.v1.json",
        "keywords": ["劳动合同", "工资", "用人单位", "入职", "离职", "解除劳动", "社会保险", "社保", "劳动仲裁", "加班费"],
        "issues": ["劳动关系成立及劳动合同履行", "工资、加班费、社会保险及经济补偿", "劳动关系解除与仲裁前置程序"],
    },
    "divorce": {
        "label": "离婚纠纷",
        "cause_code": "divorce",
        "template": "起诉状/要素式离婚纠纷起诉状.docx",
        "schema": "divorce_complaint.v1.json",
        "keywords": ["离婚", "夫妻感情", "共同财产", "共同债务", "子女抚养", "抚养费", "探望权", "结婚"],
        "issues": ["婚姻关系及感情确已破裂", "夫妻共同财产与共同债务分割", "子女抚养、抚养费与探望权"],
    },
    "traffic_accident": {
        "label": "机动车交通事故责任纠纷",
        "cause_code": "traffic_accident",
        "template": "起诉状/要素式机动车交通事故责任纠纷起诉状.docx",
        "schema": "traffic_accident_complaint.v1.json",
        "keywords": ["交通事故", "责任认定", "机动车", "医疗费", "误工费", "护理费", "残疾赔偿金", "交强险", "财产损失"],
        "issues": ["交通事故发生经过与责任认定", "人身损害各项赔偿（医疗费、误工费、护理费、残疾赔偿金等）", "机动车投保情况及财产损失"],
    },
    "work_injury_insurance": {
        "label": "工伤保险资格或者待遇认定",
        "cause_code": "work_injury_insurance",
        "template": "起诉状/要素式工伤保险资格或者待遇认定起诉状.docx",
        "schema": "work_injury_complaint.v1.json",
        "keywords": ["工伤", "工伤认定", "不予认定工伤", "工伤保险", "职业病", "劳动能力鉴定", "人社局", "行政复议"],
        "issues": ["职工与用人单位是否存在劳动关系", "事故伤害或职业病发生及工伤认定决定", "工伤决定的违法之处与救济途径"],
    },
    "house_sale": {
        "label": "房屋买卖合同纠纷",
        "cause_code": "house_sale",
        "template": "起诉状/要素式房屋买卖合同纠纷起诉状.docx",
        "schema": "house_sale_complaint.v1.json",
        "keywords": ["房屋买卖", "购房款", "商品房", "首付款", "定金", "交房", "不动产登记", "房产证", "中介服务费"],
        "issues": ["房屋买卖合同关系成立与效力", "购房款支付、房屋交付与登记", "违约责任与质量损害赔偿"],
    },
    "house_lease": {
        "label": "房屋租赁合同纠纷",
        "cause_code": "house_lease",
        "template": "起诉状/要素式房屋租赁合同纠纷起诉状.docx",
        "schema": "house_lease_complaint.v1.json",
        "keywords": ["房屋租赁", "租赁合同", "出租人", "承租人", "租金", "押金", "租赁期限", "占有使用费", "转租"],
        "issues": ["租赁合同成立与租赁期限、租金约定", "租金支付与逾期、押金返还", "合同解除与租赁物返还、占有使用费"],
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
}


def _json_object(raw: str) -> dict[str, Any]:
    """从 LLM 输出中提取第一个完整 JSON 对象（含智能引号归一化）。

    共享 helper：material_agent 与 drafting_agent 都用它解析结构化输出。
    """
    text = raw.replace("“", '"').replace("”", '"').strip()
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
