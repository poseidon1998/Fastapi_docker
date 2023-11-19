FROM python:3.9

WORKDIR /apps

COPY . /apps 

RUN pip install --no-cache-dir --upgrade -r /apps/requirements.txt

EXPOSE 90

