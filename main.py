import sys

if __name__ == '__main__':
    if '--self-check' in sys.argv:
        from cosfolio.selfcheck import run
        run()
    else:
        from cosfolio.app import main
        main()
