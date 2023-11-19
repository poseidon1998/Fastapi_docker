run docker
        -- docker run -it -v /home/hbp/code/fastApi:/apps --name fastApi -p 90:90 fastapi-fastapi:latest

run uvicorn
        -- uvicorn main:app --reload --port 90 --host 0.0.0.0
        