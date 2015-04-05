from examples import load_api
import pyservice

client = pyservice.Client(**load_api('echo/api.json'))


if __name__ == "__main__":
    response = client.greet(name="Joe", city="Seattle")
    print(response.greeting)
    print(response.question)

    try:
        client.echo(value="this will throw auth failure")
    except client.exceptions.Unauthorized as exception:
        print("Must provide credentials to call `echo`.")
