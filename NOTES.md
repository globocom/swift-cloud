# Bucket Creation

- bucket name
    globaly-unique

- location-type
    region
    dual-region
    multi-region

- default storage class
    standard
    nearline
    coldline
    archive

- object access control
    fine-grained
    uniform

- advanced
    encryption
    retention policy
    labels



curl -H 'X-Auth-Token:gAAAAABgUQjAxIEquL_SqTZEmQ5mkclRpUfn2aKsLWMgtGAYXTgh7npz7-Q3bAJKvQ_G-RZkSJ2XGgc2O2-RPd3_Ao6CXlkhQW_3Qym92a4lz7IO8qsUrPghhKfQQZKI4he6L3q3HLPoRumGH560UvICgakzt5jwqhrkJadD1InEjHhJ3gHrgkQ' http://localhost:8080


# token v3
curl -i -H 'Content-type: application/json' \
    -d '{
        "auth": {
            "identity": {
                "methods": [
                    "password"
                ],
                "password": {
                    "user": {
                        "name": "u_test",
                        "password": "u_test",
                        "domain": {
                            "name": "default"
                        }
                    }
                }
            },
            "scope": {
                "project": {
                    "name": "test",
                    "domain": {
                        "name": "default"
                    }
                }
            }
        }
    }' http://localhost:5000/v3/auth/tokens


# token v2.0
curl -k -H 'Content-type: application/json' -d '{"auth": {"tenantName": "test", "passwordCredentials": {"username": "u_test", "password": "u_test"}}}' https://localhost:5000/v2.0/tokens | python -m json.tool

