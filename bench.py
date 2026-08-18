import argparse
import re
import time
from pathlib import Path
import asyncio
import aiohttp

from dataclasses import dataclass, field


URL_PATTERN=re.compile(r"(http|https):\/\/(.+)")

@dataclass
class RequestRes:
    success:int=0
    failed:int=0
    errors:int=0
    times:list[float]=field(default_factory=list)

@dataclass
class HostStatistic:
    host:str
    res:RequestRes

    def minimum(self)->float:
        return min(self.res.times) if self.res.times else 0

    def maximum(self)->float:
        return max(self.res.times) if self.res.times else 0

    def average(self)->float:
        return (sum(self.res.times)/len(self.res.times))if self.res.times else 0




def pars_elements():
    parser = argparse.ArgumentParser()
    host_group = parser.add_mutually_exclusive_group(required=True)
    host_group.add_argument("-H",'--host',help="Список хостов через запятую")
    host_group.add_argument("-F",'--file',help="Путь до файла ср спискрм адресов")
    parser.add_argument("-C", "--count", type=int, default=1,help="количество запросов")
    parser.add_argument("-O","--output",help="путь до файла куда нужно сохранить вывод")
    args = parser.parse_args()
    return args

def validate_count(count)->int:
    if count <= 0:
        raise ValueError("Количество запросов должно быть больше 0")
    return count

def parse_hosts(hosts)->list[str]:
    result = []
    for host in hosts:
        host=host.strip()
        if not bool(URL_PATTERN.fullmatch(host)):
            raise ValueError(f"Некорректный адрес: {host}.",
                             f"Ожидается URL вида https://example.com")
        result.append(host.rstrip("/"))
    if not result:
        raise ValueError('Не указаны хосты')
    return result

def read_hosts_from_file(file)->list[str]:
    hosts=Path(file)
    if not hosts.exists():
        raise ValueError('Файл не найден')
    if not  hosts.is_file():
        raise ValueError('Путь не является файлом')
    return parse_hosts(hosts.read_text(encoding='utf-8').splitlines())






def get_hosts(args:argparse.Namespace)->list[str]:
    if args.host:
        hosts = args.host.split(',')
        return parse_hosts(hosts)
    if args.file:
        return read_hosts_from_file(args.file)

async def make_request(session:aiohttp.ClientSession, host:str, result:RequestRes)->None:
    start=time.perf_counter()
    try:
        async with session.get(host) as resp:
            await resp.read()
            result.times.append(time.perf_counter()-start)
            if 400<= resp.status <600:
                result.failed += 1
            else:
                result.success += 1
    except(aiohttp.ClientError,asyncio.TimeoutError) :
        result.errors += 1


async def check_host(session: aiohttp.ClientSession, host: str, count: int) -> HostStatistic:
    result=RequestRes()
    tasks = [make_request(session,host,result) for _ in range(count)]
    await asyncio.gather(*tasks)
    return HostStatistic(host=host, res=result)


async def run_bench(hosts:list[str],count:int)->list[HostStatistic]:
    connector=aiohttp.TCPConnector(limit=100)
    headers = {"User-Agent": "User"}
    async with aiohttp.ClientSession(connector=connector,headers=headers) as session:
        tasks=[check_host(session, host,count) for host in hosts]
        return await asyncio.gather(*tasks)

def format_statistics(statistics:list[HostStatistic])->str:
    output=[]

    for stat in statistics:
        output.append(f"Host:{stat.host}")
        output.append(f"Success:{stat.res.success}")
        output.append(f"Failed:{stat.res.failed}")
        output.append(f"Errors:{stat.res.errors}")
        output.append(f"Min:{stat.minimum():.3f}")
        output.append(f"Max:{stat.maximum():.3f}")
        output.append(f"Avg:{stat.average():.3f}")
        output.append('\n')

    return "\n".join(output)

def save_output(path: str|None, output:str)->None:
    if not path:
        print(output)
        return

    p=Path(path)

    try:
        p.write_text(output+"\n",encoding="utf-8")
    except OSError:
        raise ValueError("Не удалось записать результат")



def main():
    args = pars_elements()
    try :
        count=validate_count(args.count)
        host = get_hosts(args)
        stat=asyncio.run(run_bench(hosts=host, count=count))
        output=format_statistics(stat)
        save_output(path=args.output,output=output)
    except ValueError as exc :
        print(f"Ошибка: {exc}")
    return


if __name__ == "__main__":
    main()