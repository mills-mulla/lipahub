from .phone import mask_msisdn

PHONE_KEYS = {"msisdn", "phonenumber", "phone", "phone_number", "mobile", "mobile_number", "subscriber_msisdn"}

def scrub(obj):
    """
    copy obj with phone numbers masked
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in PHONE_KEYS and not isinstance(v, (dict ,list)):
                out[k] = mask_msisdn(v)
            else:
                out[k] = scrub(v)
        if str(obj.get("Name", "")).lower() in PHONE_KEYS and "Value" in obj:
            out["Value"] = mask_msisdn(obj.get("Value"))
    
    if isinstance(obj, list):
        return [scrub(i) for i in obj]
    return obj