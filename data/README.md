# data

Two kinds of things live here.

**Reference tables** (tracked in git) sit at the top of this folder, such as item sizes and truck dimensions. List the source of every table in the top-level README.

**Demo media** (never tracked) sits in the subfolders. Git keeps only the folder structure: a `.gitignore` in `Inputs/` and `NYPenn/` ignores every photo and clip. Share the files between us directly.

```
data/
├── Inputs/          source rooms to pack up
│   ├── Living Room/ a home living room (home footage)
│   └── Malin/       lounge space, filmed on event day
└── NYPenn/          destination: Penn Station concourse
```

To add a new room, make a folder under `Inputs/` and put an empty `.gitkeep` in it so the folder shows up for everyone.
