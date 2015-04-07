from examples import load_api
import pyservice

client = pyservice.Client(**load_api('echo/api.json'))


def main():
    response = client.greet(name="Joe", city="Seattle")
    print(response.greeting)
    print(response.question)

    try:
        client.echo(value="this will throw auth failure")
    except client.exceptions.Unauthorized:
        print("Must provide credentials to call `echo`.")

if __name__ == "__main__":
    main()
